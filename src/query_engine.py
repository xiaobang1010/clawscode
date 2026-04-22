from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator

from src.api_client import StreamEvent, create_stream
from src.compact import compact_if_needed
from src.hooks.types import HookContext, HookEvent
from src.hooks.executor import HookExecutor
from src.hooks.registry import HookRegistry
from src.permissions import PermissionChecker
from src.services.cache_params import save_cache_safe_params, build_cache_safe_params
from src.services.compact_engine import (
    micro_compact,
    reactive_compact,
    format_compact_summary,
    auto_compact_with_priority,
)
from src.services.token_budget import DiminishingReturnDetector
from src.services.token_counter import count_tokens
from src.services.tool_result_storage import apply_tool_result_budget
from src.state import SessionState
from src.tool import PermissionResult, Tool, ToolResult, truncate_output
from src.utils.git import is_git_repo, has_changes, create_checkpoint


class Transition(Enum):
    NEXT_TURN = "next_turn"
    COMPLETED = "completed"
    MAX_OUTPUT_TOKENS_RECOVERY = "max_output_tokens_recovery"
    REACTIVE_COMPACT_RETRY = "reactive_compact_retry"
    STOP_HOOK_BLOCKING = "stop_hook_blocking"
    ABORTED = "aborted"


MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3


@dataclass
class QueryState:
    messages: list[dict] = field(default_factory=list)
    transition: Transition = Transition.NEXT_TURN
    max_output_tokens_recovery_count: int = 0
    stop_hook_active: bool = False
    last_compact_tokens_before: int = 0
    last_compact_tokens_after: int = 0
    active_skill_tools: list[str] | None = None


def _create_hook_context(
    event: HookEvent,
    context: Any,
    tool_name: str = "",
    tool_input: dict | None = None,
    tool_output: str = "",
) -> HookContext:
    return HookContext(
        event=event,
        tool_name=tool_name,
        tool_input=tool_input or {},
        tool_output=tool_output,
        session_id=getattr(context, "session_id", ""),
        messages=getattr(context, "messages", []),
    )


async def ask_user_permission(
    tool: Tool,
    tool_input: Any,
    context: Any,
    permission_checker: PermissionChecker | None = None,
) -> ToolResult | None:
    print(f"\n[权限请求] {tool.name} 想要执行：{tool_input}")
    answer = input("允许？(y/n/a=always): ").strip().lower()
    if answer == "a":
        if permission_checker is not None:
            permission_checker.add_allow_rule(f"{tool.name}:*")
        return await tool.call(tool_input, context)
    elif answer == "y":
        return await tool.call(tool_input, context)
    return None


async def create_query_loop(
    user_messages: list[dict],
    tools: list[Tool],
    context: Any,
    history: list[dict],
    system_prompt: str,
    permission_checker: PermissionChecker | None = None,
    hook_executor: HookExecutor | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    state = QueryState(messages=list(history) + user_messages)
    _diminishing_detector = DiminishingReturnDetector()

    context.session_state = SessionState.RUNNING

    if hook_executor is not None:
        hook_ctx = _create_hook_context(HookEvent.SESSION_START, context)
        await hook_executor.execute(hook_ctx)

    while True:
        transition = await _run_one_turn(
            state, tools, context, system_prompt,
            permission_checker, hook_executor, _diminishing_detector,
        )

        if transition == Transition.COMPLETED:
            if hook_executor is not None:
                stop_result = await _execute_stop_hooks(hook_executor, context)
                if stop_result.get("prevent_continuation"):
                    context.session_state = SessionState.IDLE
                    break
                if stop_result.get("blocking_error"):
                    state.messages.append({
                        "role": "user",
                        "content": f"[Stop Hook 反馈] {stop_result['blocking_error']}",
                    })
                    state.stop_hook_active = True
                    continue

            context.session_state = SessionState.IDLE
            break

        elif transition == Transition.ABORTED:
            context.session_state = SessionState.IDLE
            break

        elif transition == Transition.MAX_OUTPUT_TOKENS_RECOVERY:
            if state.max_output_tokens_recovery_count < MAX_OUTPUT_TOKENS_RECOVERY_LIMIT:
                state.messages.append({
                    "role": "user",
                    "content": "请继续生成，从中断处恢复。不要重复已生成的内容。",
                })
                state.max_output_tokens_recovery_count += 1
            else:
                context.session_state = SessionState.IDLE
                break

        elif transition == Transition.REACTIVE_COMPACT_RETRY:
            try:
                compacted = await reactive_compact(
                    state.messages,
                    context.settings.effective_max_tokens,
                    create_stream_fn=create_stream,
                )
                state.messages = compacted
            except Exception:
                context.session_state = SessionState.IDLE
                break

        elif transition == Transition.STOP_HOOK_BLOCKING:
            continue

        elif transition == Transition.NEXT_TURN:
            state.max_output_tokens_recovery_count = 0
            state.stop_hook_active = False


async def _run_one_turn(
    state: QueryState,
    tools: list[Tool],
    context: Any,
    system_prompt: str,
    permission_checker: PermissionChecker | None,
    hook_executor: HookExecutor | None,
    diminishing_detector: DiminishingReturnDetector | None = None,
) -> Transition:
    active_tools = [t for t in tools if not getattr(t, "is_lazy", False)]
    if state.active_skill_tools is not None:
        active_tools = [t for t in active_tools if t.name in state.active_skill_tools]
    tool_schemas = [t.get_openai_tool_schema() for t in active_tools]
    tool_map = {t.name: t for t in active_tools}

    if not state.stop_hook_active:
        await _maybe_proactive_compact(state, context, hook_executor, diminishing_detector)

    has_tool_calls = False
    current_tool_calls: dict[int, dict] = {}
    finish_reason = None

    try:
        async for event in create_stream(
            state.messages,
            tool_schemas,
            system_prompt,
            model=context.settings.model,
            api_key=context.settings.api_key,
            base_url=context.settings.base_url,
        ):
            yield_placeholder = event

            if event.type == "tool_calls":
                has_tool_calls = True
                idx = event.data.get("index", 0)
                if idx not in current_tool_calls:
                    current_tool_calls[idx] = {
                        "id": event.data["id"],
                        "name": event.data["name"],
                        "arguments": "",
                    }
                current_tool_calls[idx]["arguments"] += event.data.get("arguments") or ""

            if event.type == "usage":
                svc = getattr(context, "cost_tracker_service", None)
                if svc is not None:
                    svc.record(
                        input_tokens=event.data.get("input_tokens", 0),
                        output_tokens=event.data.get("output_tokens", 0),
                        model=event.data.get("model"),
                        duration_ms=event.data.get("duration_ms", 0),
                    )

            if event.type == "finish_reason":
                finish_reason = event.data.get("reason")

        save_cache_safe_params(build_cache_safe_params(
            system_prompt=system_prompt,
            tools=tool_schemas,
            messages=state.messages,
            model=context.settings.model if hasattr(context, "settings") else "",
            base_url=context.settings.base_url if hasattr(context, "settings") else "",
            api_key=context.settings.api_key if hasattr(context, "settings") else "",
            prefix_count=2,
        ))
    except Exception as e:
        error_str = str(e).lower()
        if any(kw in error_str for kw in ["prompt_too_long", "context_length", "max.*token", "too many tokens"]):
            return Transition.REACTIVE_COMPACT_RETRY
        raise

    if finish_reason == "length":
        assistant_text = _collect_text_from_messages(current_tool_calls)
        state.messages.append({
            "role": "assistant",
            "content": assistant_text or None,
            "tool_calls": _build_tool_calls_content(current_tool_calls) if has_tool_calls else None,
        })
        return Transition.MAX_OUTPUT_TOKENS_RECOVERY

    if not has_tool_calls:
        return Transition.COMPLETED

    for idx in sorted(current_tool_calls):
        tc = current_tool_calls[idx]

    assistant_content = []
    for idx in sorted(current_tool_calls):
        tc = current_tool_calls[idx]
        assistant_content.append(
            {
                "type": "function",
                "id": tc["id"],
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
        )

    sorted_tcs = [current_tool_calls[idx] for idx in sorted(current_tool_calls)]
    results = await _execute_tools(
        sorted_tcs, tool_map, context, permission_checker, hook_executor,
    )

    state.messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": assistant_content,
        }
    )

    for tc, result in results:
        if result.metadata and "allowed_tools" in result.metadata:
            state.active_skill_tools = result.metadata["allowed_tools"]

    for tc, result in results:
        state.messages.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result.output,
            }
        )

    for tc, result in results:
        tool = tool_map.get(tc["name"])
        if tool is not None and tool.name in ("FileEdit", "FileWrite") and not result.is_error:
            pass

    return Transition.NEXT_TURN


async def _maybe_proactive_compact(
    state: QueryState,
    context: Any,
    hook_executor: HookExecutor | None,
    diminishing_detector: DiminishingReturnDetector | None = None,
) -> None:
    from src.services.token_budget import infer_context_window
    settings = getattr(context, 'settings', None)
    if settings:
        max_ctx = settings.effective_max_tokens
    else:
        max_ctx = 128000
    est_tokens = count_tokens(state.messages)

    if est_tokens <= max_ctx * 0.8:
        return

    state.last_compact_tokens_before = est_tokens

    if hook_executor is not None:
        pre_ctx = _create_hook_context(HookEvent.PRE_COMPACT, context)
        await hook_executor.execute(pre_ctx)

    state.messages = await auto_compact_with_priority(state.messages, max_ctx, create_stream_fn=create_stream)

    if hook_executor is not None:
        post_ctx = _create_hook_context(HookEvent.POST_COMPACT, context)
        await hook_executor.execute(post_ctx)

    state.messages = micro_compact(state.messages)
    state.messages = apply_tool_result_budget(state.messages)
    state.last_compact_tokens_after = count_tokens(state.messages)

    saved = state.last_compact_tokens_before - state.last_compact_tokens_after
    if diminishing_detector is not None:
        diminishing_detector.record(max(0, saved))
        if diminishing_detector.is_diminishing():
            state.messages.append({
                "role": "user",
                "content": "[系统提示] 上下文压缩效果递减，建议使用 /compact 手动压缩或重启会话。",
            })

    est_tokens = state.last_compact_tokens_after
    if est_tokens > max_ctx * 0.9:
        non_system = [m for m in state.messages if m.get("role") != "system"]
        system = [m for m in state.messages if m.get("role") == "system"]
        trim_count = max(1, len(non_system) // 4)
        state.messages = system + non_system[trim_count:]


async def _execute_tools(
    tool_calls: list[dict],
    tool_map: dict[str, Tool],
    context: Any,
    permission_checker: PermissionChecker | None,
    hook_executor: HookExecutor | None,
) -> list[tuple[dict, ToolResult]]:

    async def _execute_one(tc: dict) -> tuple[dict, ToolResult]:
        tool = tool_map.get(tc["name"])
        if tool is None:
            return tc, ToolResult(
                output=f"工具 '{tc['name']}' 当前不可用（已延迟加载）",
                is_error=True,
            )

        if tool.name in ("FileEdit", "FileWrite"):
            cwd = getattr(context, "cwd", None)
            if cwd is not None and is_git_repo(cwd):
                if has_changes(cwd):
                    context.checkpoint_count += 1
                    create_checkpoint(cwd, context.checkpoint_count)

        tool_input = tool.input_schema(**json.loads(tc["arguments"]))

        if hook_executor is not None:
            pre_ctx = _create_hook_context(
                HookEvent.PRE_TOOL_USE, context,
                tool_name=tool.name,
                tool_input=tc.get("parsed_args", json.loads(tc["arguments"])),
            )
            pre_result = await hook_executor.execute_and_collect(pre_ctx)
            if pre_result.should_block:
                return tc, ToolResult(
                    output=f"操作被 Hook 阻止: {pre_result.output}",
                    is_error=True,
                )

        if permission_checker is not None:
            perm = await permission_checker.check(tool, tool_input, context)
        else:
            perm = await tool.check_permissions(tool_input, context)

        if perm == PermissionResult.DENY:
            result = ToolResult(output="操作被拒绝", is_error=True)
        elif perm == PermissionResult.ASK:
            context.session_state = SessionState.REQUIRES_ACTION
            result = await ask_user_permission(tool, tool_input, context, permission_checker)
            context.session_state = SessionState.RUNNING
            if result is None:
                result = ToolResult(output="用户拒绝了操作", is_error=True)
        else:
            result = await tool.call(tool_input, context)

        max_chars = getattr(tool, "max_result_size_chars", 25000)
        if len(result.output) > max_chars:
            result = result.truncate(max_chars)

        if hook_executor is not None:
            post_ctx = _create_hook_context(
                HookEvent.POST_TOOL_USE, context,
                tool_name=tool.name,
                tool_input=json.loads(tc["arguments"]),
                tool_output=result.output,
            )
            await hook_executor.execute(post_ctx)

        return tc, result

    return await asyncio.gather(*[_execute_one(tc) for tc in tool_calls])


async def _execute_stop_hooks(
    hook_executor: HookExecutor,
    context: Any,
) -> dict[str, Any]:
    stop_ctx = _create_hook_context(HookEvent.STOP, context)
    results = await hook_executor.execute(stop_ctx)

    blocking_error = ""
    prevent_continuation = False

    for result in results:
        if result.should_block:
            if result.output:
                blocking_error += result.output + "\n"
            if result.metadata.get("prevent_continuation"):
                prevent_continuation = True

    return {
        "blocking_error": blocking_error.strip(),
        "prevent_continuation": prevent_continuation,
    }


def _collect_text_from_messages(tool_calls: dict[int, dict]) -> str:
    return ""


def _build_tool_calls_content(tool_calls: dict[int, dict]) -> list[dict]:
    content = []
    for idx in sorted(tool_calls):
        tc = tool_calls[idx]
        content.append(
            {
                "type": "function",
                "id": tc["id"],
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
        )
    return content
