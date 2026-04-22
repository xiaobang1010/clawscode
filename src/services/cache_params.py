from __future__ import annotations

import hashlib
import json
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
    user_context: dict[str, str] = field(default_factory=dict)
    system_context: dict[str, str] = field(default_factory=dict)
    fork_context_messages: list[dict] = field(default_factory=list)


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
    user_context: dict[str, str] | None = None,
    system_context: dict[str, str] | None = None,
    fork_context_messages: list[dict] | None = None,
) -> CacheSafeParams:
    prefix = messages[:prefix_count] if prefix_count > 0 else []
    return CacheSafeParams(
        system_prompt=system_prompt,
        tools=tools,
        messages_prefix=prefix,
        model=model,
        base_url=base_url,
        api_key=api_key,
        user_context=user_context or {},
        system_context=system_context or {},
        fork_context_messages=fork_context_messages or [],
    )


def compute_cache_key(params: CacheSafeParams) -> str:
    key_data = {
        "system_prompt": params.system_prompt,
        "tools": params.tools,
        "messages_prefix": params.messages_prefix,
        "model": params.model,
    }
    key_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(key_str.encode()).hexdigest()


def cache_params_match(a: CacheSafeParams, b: CacheSafeParams) -> bool:
    return (
        a.system_prompt == b.system_prompt
        and a.tools == b.tools
        and a.model == b.model
        and a.messages_prefix == b.messages_prefix
    )
