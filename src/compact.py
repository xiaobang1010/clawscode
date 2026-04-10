from __future__ import annotations

from src.services.token_counter import count_tokens

AUTOCOMPACT_BUFFER_TOKENS = 13000
WARNING_THRESHOLD_TOKENS = 20000
MAX_CONSECUTIVE_FAILURES = 3
MIN_RECENT_MESSAGES = 10

_consecutive_failures = 0


async def compact_if_needed(messages: list[dict], max_tokens: int) -> list[dict]:
    global _consecutive_failures

    used = count_tokens(messages)
    buffer = max_tokens - used

    if buffer >= WARNING_THRESHOLD_TOKENS:
        return messages

    if _consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        print("[警告] 上下文接近上限，自动压缩已禁用")
        return messages

    try:
        system = [m for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]

        target_tokens = max_tokens - AUTOCOMPACT_BUFFER_TOKENS
        recent_count = len(non_system)
        for n in range(MIN_RECENT_MESSAGES, len(non_system) + 1):
            candidate = system + non_system[-n:]
            if count_tokens(candidate) <= target_tokens:
                recent_count = n
                break
        else:
            recent_count = MIN_RECENT_MESSAGES

        compacted = system + non_system[-recent_count:]
        _consecutive_failures = 0
        return compacted
    except Exception:
        _consecutive_failures += 1
        return messages
