from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from src.api_client import StreamEvent, create_stream
from src.compact import compact_if_needed
from src.hooks.types import HookContext, HookEvent
from src.hooks.executor import HookExecutor
from src.hooks.registry import HookRegistry
from src.permissions import PermissionChecker
from src.state import SessionState
from src.tool import PermissionResult, Tool, ToolResult, truncate_output
from src.utils.git import is_git_repo, has_changes, create_checkpoint


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
    messages = list(history) + user_messages

    context.session_state = SessionState.RUNNING

    if hook_executor is not None:
        hook_ctx = _create_hook_context(HookEvent.SESSION_START, context)
        await hook_executor.execute(hook_ctx)

    while True:
        tool_schemas = [t.get_openai_tool_schema() for t in tools]
        tool_map = {t.name: t for t in tools}

        has_tool_calls = False
        current_tool_calls: dict[int, dict] = {}

        est_tokens = sum(len(json.dumps(m, ensure_ascii=False)) // 4 for m in messages)
        max_ctx = getattr(context.settings, 'max_tokens', 128000) if hasattr(context, 'settings') else 128000
        if est_tokens > max_ctx * 0.8:
            if hook_executor is not None:
                pre_ctx = _create_hook_context(HookEvent.PRE_COMPACT, context)
                await hook_executor.execute(pre_ctx)

            messages = await compact_if_needed(messages, max_ctx, create_stream_fn=create_stream)

            if hook_executor is not None:
                post_ctx = _create_hook_context(HookEvent.POST_COMPACT, context)
                await hook_executor.execute(post_ctx)

            est_tokens = sum(len(json.dumps(m, ensure_ascii=False)) // 4 for m in messages)
            if est_tokens > max_ctx * 0.9:
                trim_count = max(1, len([m for m in messages if m.get("role") != "system"]) // 4)
                non_system = [m for m in messages if m.get("role") != "system"]
                messages = [m for m in messages if m.get("role") == "system"] + non_system[trim_count:]

        async for event in create_stream(
            messages,
            tool_schemas,
            system_prompt,
            model=context.settings.model,
            api_key=context.settings.api_key,
            base_url=context.settings.base_url,
        ):
            yield event

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

        if not has_tool_calls:
            if hook_executor is not None:
                stop_ctx = _create_hook_context(HookEvent.STOP, context)
                await hook_executor.execute(stop_ctx)
            context.session_state = SessionState.IDLE
            break

        for idx in sorted(current_tool_calls):
            tc = current_tool_calls[idx]
            yield StreamEvent(
                type="tool_call_summary",
                data={"name": tc["name"], "arguments": tc["arguments"]},
            )

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

        async def _execute_tool(tc: dict) -> tuple[dict, ToolResult]:
            tool = tool_map[tc["name"]]

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

        sorted_tcs = [current_tool_calls[idx] for idx in sorted(current_tool_calls)]
        results = await asyncio.gather(*[_execute_tool(tc) for tc in sorted_tcs])

        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": assistant_content,
            }
        )

        for tc, result in results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result.output,
                }
            )

        for tc, result in results:
            tool = tool_map[tc["name"]]
            if tool.name in ("FileEdit", "FileWrite") and not result.is_error:
                yield StreamEvent(type="checkpoint", data={"index": context.checkpoint_count})

        if hook_executor is not None:
            pre_compact_ctx = _create_hook_context(HookEvent.PRE_COMPACT, context)
            await hook_executor.execute(pre_compact_ctx)

        messages = await compact_if_needed(messages, context.settings.max_tokens, create_stream_fn=create_stream)

        if hook_executor is not None:
            post_compact_ctx = _create_hook_context(HookEvent.POST_COMPACT, context)
            await hook_executor.execute(post_compact_ctx)
