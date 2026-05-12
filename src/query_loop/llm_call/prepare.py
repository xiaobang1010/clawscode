from __future__ import annotations

from typing import Any

from src.query_loop.state import QueryState
from src.services.compact_engine import cached_micro_compact, consume_pending_cache_edits
from src.services.message_normalizer import ensure_tool_result_pairing, normalize_messages_for_api
from src.services.message_tombstone import filter_tombstone_messages


def prepare_messages(state: QueryState) -> tuple[list[dict], dict[str, Any]]:
    """预处理消息：过滤、标准化、配对修正，并构建 cache_edits 相关参数。"""
    filtered_messages = filter_tombstone_messages(state.messages)
    normalized_messages = normalize_messages_for_api(filtered_messages)
    normalized_messages = ensure_tool_result_pairing(normalized_messages)

    cached_micro_compact(state.messages)
    cache_edits_block = consume_pending_cache_edits()

    stream_kwargs: dict[str, Any] = {}
    if cache_edits_block is not None:
        stream_kwargs["cache_edits"] = [
            {"type": e.get("type", "cache_delete"), "tool_use_id": e.get("tool_use_id", "")}
            for e in cache_edits_block.edits
        ]
        stream_kwargs["cache_reference"] = cache_edits_block.cache_reference

    return normalized_messages, stream_kwargs
