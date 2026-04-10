from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _get_encoder():
    return tiktoken.encoding_for_model("gpt-4")


def count_tokens(messages: list[dict]) -> int:
    enc = _get_encoder()
    total = 0
    for msg in messages:
        total += len(enc.encode(str(msg)))
    return total
