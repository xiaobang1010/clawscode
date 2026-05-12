from __future__ import annotations

from typing import TYPE_CHECKING

from src.api_client import create_stream
from src.services.compact_engine import reactive_compact

if TYPE_CHECKING:
    from src.query_loop.state import QueryState


async def reactive_compact_call(state: QueryState, max_tokens: int) -> bool:
    """被动压缩：上下文溢出时的应急压缩，返回是否成功"""
    try:
        compacted = await reactive_compact(
            state.messages,
            max_tokens,
            create_stream_fn=create_stream,
        )
        state.messages = compacted
        return True
    except Exception:
        return False


async def collapse_drain_recover(state: QueryState, max_tokens: int) -> bool:
    """先尝试 collapse drain 恢复，失败则回退到被动压缩，返回是否成功"""
    try:
        from src.services.context_collapse import recover_from_overflow
        from src.services.token_counter import count_tokens as _ct

        token_usage = _ct(state.messages)
        result = recover_from_overflow(
            state.messages,
            token_usage,
            max_tokens,
        )
        if result["committed"] > 0:
            state.messages = result["messages"]
        else:
            compacted = await reactive_compact(
                state.messages,
                max_tokens,
                create_stream_fn=create_stream,
            )
            state.messages = compacted
        return True
    except Exception:
        return False
