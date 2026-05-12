from __future__ import annotations

from typing import TYPE_CHECKING

from src.services.compact_engine import micro_compact
from src.services.history_snip import get_snipped_messages, snip_message
from src.services.token_counter import count_tokens
from src.services.tool_result_storage import apply_tool_result_budget

if TYPE_CHECKING:
    from src.query_loop.state import QueryState
    from src.services.token_budget import DiminishingReturnDetector


def run_post_compact_pipeline(
    state: QueryState,
    diminishing_detector: DiminishingReturnDetector | None,
    max_ctx: int,
) -> None:
    """执行主动压缩后的后处理流水线：micro_compact → tool_result_budget → history_snip → 递减检测 → 超90%裁剪"""
    state.messages = micro_compact(state.messages)
    state.messages = apply_tool_result_budget(state.messages)

    # 处理被 snip 标记的消息
    snipped = get_snipped_messages(state.messages)
    if snipped:
        for s in snipped:
            state.messages = snip_message(state.messages, s.get("uuid", ""))

    state.last_compact_tokens_after = count_tokens(state.messages)

    # 递减检测
    saved = state.last_compact_tokens_before - state.last_compact_tokens_after
    if diminishing_detector is not None:
        diminishing_detector.record(max(0, saved))
        if diminishing_detector.is_diminishing():
            state.messages.append({
                "role": "user",
                "content": "[系统提示] 上下文压缩效果递减，建议使用 /compact 手动压缩或重启会话。",
            })

    # 压缩后仍超过 90% 则强制裁剪
    est_tokens = state.last_compact_tokens_after
    if est_tokens > max_ctx * 0.9:
        non_system = [m for m in state.messages if m.get("role") != "system"]
        system = [m for m in state.messages if m.get("role") == "system"]
        trim_count = max(1, len(non_system) // 4)
        state.messages = system + non_system[trim_count:]
