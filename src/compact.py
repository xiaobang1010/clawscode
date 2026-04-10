from __future__ import annotations

AUTOCOMPACT_BUFFER_TOKENS = 13000
WARNING_THRESHOLD_TOKENS = 20000
MAX_CONSECUTIVE_FAILURES = 3

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
        recent = [m for m in messages if m["role"] != "system"][-20:]
        compacted = system + recent
        _consecutive_failures = 0
        return compacted
    except Exception:
        _consecutive_failures += 1
        return messages


def count_tokens(messages: list[dict]) -> int:
    import tiktoken

    enc = tiktoken.encoding_for_model("gpt-4")
    total = 0
    for msg in messages:
        total += len(enc.encode(str(msg)))
    return total
