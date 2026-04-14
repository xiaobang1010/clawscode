from __future__ import annotations

from src.services.compact_engine import (
    compact_if_needed as _compact_if_needed,
    compact_with_llm,
    apply_compaction,
    build_compact_messages,
    build_partial_compact_messages,
    create_compact_boundary_message,
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


async def compact_if_needed(messages: list[dict], max_tokens: int) -> list[dict]:
    return _compact_if_needed(messages, max_tokens)
