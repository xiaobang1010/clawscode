from __future__ import annotations

from typing import Any

from src.services.compact_engine import (
    compact_if_needed as _compact_if_needed,
    compact_with_llm,
    reactive_compact,
    apply_compaction,
    build_compact_messages,
    build_partial_compact_messages,
    create_compact_boundary_message,
    format_compact_summary,
    is_compact_boundary,
    AUTOCOMPACT_BUFFER_TOKENS,
    WARNING_THRESHOLD_TOKENS,
    MAX_CONSECUTIVE_FAILURES,
    MIN_RECENT_MESSAGES,
    BASE_COMPACT_PROMPT,
    PARTIAL_COMPACT_PROMPT,
    NO_TOOLS_PREAMBLE,
    COMPACT_BOUNDARY_PREFIX,
)


async def compact_if_needed(
    messages: list[dict],
    max_tokens: int,
    create_stream_fn: Any = None,
) -> list[dict]:
    if create_stream_fn is not None:
        return await compact_with_llm(
            messages, max_tokens, create_stream_fn=create_stream_fn
        )
    return _compact_if_needed(messages, max_tokens)
