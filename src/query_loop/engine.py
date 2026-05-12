from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator

from src.api_client import StreamEvent
from src.hooks.types import HookContext, HookEvent
from src.hooks.executor import HookExecutor
from src.permissions import PermissionChecker
from src.services.agent_context import FileStateCache, ToolUseContext
from src.services.cache_params import save_cache_safe_params, build_cache_safe_params, CacheSafeParams
from src.services.token_budget import DiminishingReturnDetector
from src.state import SessionState
from src.tool import Tool, ToolResult

from src.query_loop.state import (
    Transition, QueryState, QueryEngineConfig, MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
)
from src.query_loop.compact import proactive_compact, reactive_compact_call, collapse_drain_recover
from src.query_loop.llm_call import prepare_messages, call_llm, LLMResult, CompactRetryError, CollapseRetryError
from src.query_loop.tool_exec import execute_tools, execute_stop_hooks, create_hook_context
from src.query_loop.message import (
    append_assistant_message, append_tool_results,
    build_tool_calls_content, collect_text_from_messages,
)


def _build_hook_executor(state: Any) -> HookExecutor | None:
    if getattr(state, 'hook_snapshot', None) is not None:
        return state.hook_snapshot
    settings_dict: dict[str, Any] | None = None
    if hasattr(state, 'settings') and hasattr(state.settings, 'hooks'):
        hooks_cfg = state.settings.hooks
        if not hooks_cfg.enabled:
            return None
        settings_dict = {"hooks": hooks_cfg.hooks}
    try:
        from src.boot.hooks import build_hook_snapshot
        executor = build_hook_snapshot(state.settings)
        state.hook_snapshot = executor
        return executor
    except Exception:
        pass
    return None


async def handle_query(
    user_input: str,
    state: Any,
    system_prompt: str,
    permission_checker: PermissionChecker | None = None,
    extra_tools: list[Tool] | None = None,
    hook_executor: HookExecutor | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    from src.tools import get_tools

    tools = get_tools()
    if extra_tools is not None:
        tools = tools + extra_tools

    user_messages = [{"role": "user", "content": user_input}]
    executor = hook_executor or _build_hook_executor(state)
    if executor is not None:
        prompt_ctx = HookContext(
            event=HookEvent.USER_PROMPT_SUBMIT,
            metadata={"prompt": user_input},
            session_id=state.session_id,
        )
        await executor.execute(prompt_ctx)

    return create_query_loop(
        user_messages=user_messages,
        tools=tools,
        context=state,
        history=state.messages,
        system_prompt=system_prompt,
        permission_checker=permission_checker,
        hook_executor=executor,
    )


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
        hook_ctx = create_hook_context(HookEvent.SESSION_START, context)
        await hook_executor.execute(hook_ctx)

    while True:
        transition = await _run_one_turn(
            state, tools, context, system_prompt,
            permission_checker, hook_executor, _diminishing_detector,
        )

        if transition == Transition.COMPLETED:
            if hook_executor is not None:
                stop_result = await execute_stop_hooks(hook_executor, context)
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
            max_tokens = getattr(
                getattr(context, 'settings', None), 'effective_max_tokens', 128000,
            )
            success = await reactive_compact_call(state, max_tokens)
            if not success:
                context.session_state = SessionState.IDLE
                break

        elif transition == Transition.COLLAPSE_DRAIN_RETRY:
            max_tokens = getattr(
                getattr(context, 'settings', None), 'effective_max_tokens', 128000,
            )
            success = await collapse_drain_recover(state, max_tokens)
            if not success:
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
        await proactive_compact(state, context, hook_executor, diminishing_detector)

    try:
        normalized_messages, stream_kwargs = prepare_messages(state)
        llm_result = await call_llm(
            normalized_messages, tool_schemas, system_prompt, context, stream_kwargs,
        )
    except CompactRetryError:
        return Transition.REACTIVE_COMPACT_RETRY
    except CollapseRetryError:
        return Transition.COLLAPSE_DRAIN_RETRY

    if llm_result.finish_reason == "length":
        state.messages.append({
            "role": "assistant",
            "content": collect_text_from_messages(llm_result.tool_calls) or None,
            "tool_calls": build_tool_calls_content(llm_result.tool_calls) if llm_result.has_tool_calls else None,
        })
        return Transition.MAX_OUTPUT_TOKENS_RECOVERY

    if not llm_result.has_tool_calls:
        return Transition.COMPLETED

    sorted_tcs = [llm_result.tool_calls[idx] for idx in sorted(llm_result.tool_calls)]
    results = await execute_tools(
        sorted_tcs, tool_map, context, permission_checker, hook_executor,
    )

    append_assistant_message(state, llm_result.tool_calls, llm_result.has_tool_calls)
    append_tool_results(state, results, tool_map)

    return Transition.NEXT_TURN


class QueryEngine:
    def __init__(
        self,
        tools: list[Tool],
        context: Any,
        system_prompt: str,
        config: QueryEngineConfig | None = None,
        permission_checker: PermissionChecker | None = None,
        hook_executor: HookExecutor | None = None,
    ):
        self._tools = tools
        self._context = context
        self._system_prompt = system_prompt
        self._config = config or QueryEngineConfig()
        self._permission_checker = permission_checker
        self._hook_executor = hook_executor
        self._state = QueryState()
        self._diminishing_detector = DiminishingReturnDetector()
        self._read_file_state = FileStateCache()
        self._tool_use_context: ToolUseContext | None = None
        self._abort_event: asyncio.Event | None = None
        self._cache_safe_params: CacheSafeParams | None = None

    @property
    def messages(self) -> list[dict]:
        return self._state.messages

    @property
    def read_file_state(self) -> FileStateCache:
        return self._read_file_state

    @property
    def state(self) -> QueryState:
        return self._state

    def get_messages(self) -> list[dict]:
        return list(self._state.messages)

    def get_read_file_state(self) -> FileStateCache:
        return self._read_file_state

    def set_history(self, history: list[dict]) -> None:
        self._state.messages = list(history)

    def interrupt(self) -> None:
        if self._abort_event is not None:
            self._abort_event.set()

    async def submit_message(
        self,
        user_messages: list[dict],
    ) -> AsyncGenerator[StreamEvent, None]:
        self._state.messages.extend(user_messages)
        self._context.session_state = SessionState.RUNNING

        if self._hook_executor is not None:
            hook_ctx = self._create_hook_context(HookEvent.SESSION_START)
            await self._hook_executor.execute(hook_ctx)

        while True:
            transition = await self._run_one_turn()

            if transition == Transition.COMPLETED:
                if self._hook_executor is not None:
                    stop_result = await self._execute_stop_hooks()
                    if stop_result.get("prevent_continuation"):
                        self._context.session_state = SessionState.IDLE
                        break
                    if stop_result.get("blocking_error"):
                        self._state.messages.append({
                            "role": "user",
                            "content": f"[Stop Hook 反馈] {stop_result['blocking_error']}",
                        })
                        self._state.stop_hook_active = True
                        continue

                self._context.session_state = SessionState.IDLE
                break

            elif transition == Transition.ABORTED:
                self._context.session_state = SessionState.IDLE
                break

            elif transition == Transition.MAX_OUTPUT_TOKENS_RECOVERY:
                if self._state.max_output_tokens_recovery_count < MAX_OUTPUT_TOKENS_RECOVERY_LIMIT:
                    self._state.messages.append({
                        "role": "user",
                        "content": "请继续生成，从中断处恢复。不要重复已生成的内容。",
                    })
                    self._state.max_output_tokens_recovery_count += 1
                else:
                    self._context.session_state = SessionState.IDLE
                    break

            elif transition == Transition.REACTIVE_COMPACT_RETRY:
                success = await reactive_compact_call(self._state, self._config.max_tokens)
                if not success:
                    self._context.session_state = SessionState.IDLE
                    break

            elif transition == Transition.COLLAPSE_DRAIN_RETRY:
                success = await collapse_drain_recover(self._state, self._config.max_tokens)
                if not success:
                    self._context.session_state = SessionState.IDLE
                    break

            elif transition == Transition.STOP_HOOK_BLOCKING:
                continue

            elif transition == Transition.NEXT_TURN:
                self._state.max_output_tokens_recovery_count = 0
                self._state.stop_hook_active = False

    async def _run_one_turn(self) -> Transition:
        active_tools = [t for t in self._tools if not getattr(t, "is_lazy", False)]
        if self._state.active_skill_tools is not None:
            active_tools = [t for t in active_tools if t.name in self._state.active_skill_tools]
        tool_schemas = [t.get_openai_tool_schema() for t in active_tools]
        tool_map = {t.name: t for t in active_tools}

        if not self._state.stop_hook_active:
            await self._maybe_proactive_compact()

        try:
            normalized_messages, stream_kwargs = prepare_messages(self._state)
            llm_result = await call_llm(
                normalized_messages, tool_schemas, self._system_prompt,
                self._context, stream_kwargs,
            )
        except CompactRetryError:
            return Transition.REACTIVE_COMPACT_RETRY
        except CollapseRetryError:
            return Transition.COLLAPSE_DRAIN_RETRY

        if llm_result.finish_reason == "length":
            self._state.messages.append({
                "role": "assistant",
                "content": collect_text_from_messages(llm_result.tool_calls) or None,
                "tool_calls": build_tool_calls_content(llm_result.tool_calls) if llm_result.has_tool_calls else None,
            })
            return Transition.MAX_OUTPUT_TOKENS_RECOVERY

        if not llm_result.has_tool_calls:
            return Transition.COMPLETED

        sorted_tcs = [llm_result.tool_calls[idx] for idx in sorted(llm_result.tool_calls)]
        results = await execute_tools(
            sorted_tcs, tool_map, self._context,
            self._permission_checker, self._hook_executor,
        )

        append_assistant_message(self._state, llm_result.tool_calls, llm_result.has_tool_calls)
        append_tool_results(self._state, results, tool_map)

        return Transition.NEXT_TURN

    async def _maybe_proactive_compact(self) -> None:
        await proactive_compact(
            self._state, self._context,
            self._hook_executor, self._diminishing_detector,
        )

    async def _execute_tools(
        self,
        tool_calls: list[dict],
        tool_map: dict[str, Tool],
    ) -> list[tuple[dict, ToolResult]]:
        return await execute_tools(
            tool_calls, tool_map, self._context,
            self._permission_checker, self._hook_executor,
        )

    async def _execute_stop_hooks(self) -> dict[str, Any]:
        return await execute_stop_hooks(self._hook_executor, self._context)

    def _create_hook_context(
        self,
        event: HookEvent,
        tool_name: str = "",
        tool_input: dict | None = None,
        tool_output: str = "",
    ) -> HookContext:
        return HookContext(
            event=event,
            tool_name=tool_name,
            tool_input=tool_input or {},
            tool_output=tool_output,
            session_id=getattr(self._context, "session_id", ""),
            messages=self._state.messages,
        )
