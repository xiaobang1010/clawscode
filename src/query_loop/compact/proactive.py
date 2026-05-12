from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.api_client import create_stream
from src.hooks.types import HookContext, HookEvent
from src.services.compact_engine import auto_compact_with_priority
from src.services.token_counter import count_tokens

from src.query_loop.compact.helpers import run_post_compact_pipeline

if TYPE_CHECKING:
    from src.query_loop.state import QueryState
    from src.hooks.executor import HookExecutor
    from src.services.token_budget import DiminishingReturnDetector


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


async def proactive_compact(
    state: QueryState,
    context: Any,
    hook_executor: HookExecutor | None,
    diminishing_detector: DiminishingReturnDetector | None = None,
) -> None:
    """主动压缩：当 token 用量超过阈值 80% 时自动压缩上下文"""
    settings = getattr(context, "settings", None)
    if settings:
        max_ctx = settings.effective_max_tokens
    else:
        max_ctx = 128000
    est_tokens = count_tokens(state.messages)

    # 未超过 80% 阈值则跳过
    if est_tokens <= max_ctx * 0.8:
        return

    state.last_compact_tokens_before = est_tokens

    # 压缩前 hook
    if hook_executor is not None:
        pre_ctx = _create_hook_context(HookEvent.PRE_COMPACT, context)
        await hook_executor.execute(pre_ctx)

    # 执行自动压缩
    state.messages = await auto_compact_with_priority(
        state.messages, max_ctx, create_stream_fn=create_stream,
    )

    # 压缩后 hook
    if hook_executor is not None:
        post_ctx = _create_hook_context(HookEvent.POST_COMPACT, context)
        await hook_executor.execute(post_ctx)

    # 后处理流水线
    run_post_compact_pipeline(state, diminishing_detector, max_ctx)
