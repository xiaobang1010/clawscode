from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CacheSafeParams:
    system_prompt: str
    tools: list[dict] = field(default_factory=list)
    messages_prefix: list[dict] = field(default_factory=list)
    model: str = ""
    base_url: str = ""
    api_key: str = ""


_last_cache_safe_params: CacheSafeParams | None = None


def save_cache_safe_params(params: CacheSafeParams | None) -> None:
    global _last_cache_safe_params
    _last_cache_safe_params = params


def get_cache_safe_params() -> CacheSafeParams | None:
    return _last_cache_safe_params


def build_cache_safe_params(
    system_prompt: str,
    tools: list[dict],
    messages: list[dict],
    model: str = "",
    base_url: str = "",
    api_key: str = "",
    prefix_count: int = 0,
) -> CacheSafeParams:
    prefix = messages[:prefix_count] if prefix_count > 0 else []
    return CacheSafeParams(
        system_prompt=system_prompt,
        tools=tools,
        messages_prefix=prefix,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
