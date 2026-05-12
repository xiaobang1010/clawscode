from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.api_client import create_stream
from src.services.cache_params import build_cache_safe_params, save_cache_safe_params


class CompactRetryError(Exception):
    """上下文溢出，需要 reactive compact 后重试。"""


class CollapseRetryError(Exception):
    """上下文溢出且启用了 context collapse，需要 drain 后重试。"""


_OVERFLOW_KEYWORDS = ("prompt_too_long", "context_length", "max.*token", "too many tokens")


@dataclass
class LLMResult:
    tool_calls: dict[int, dict] = field(default_factory=dict)
    finish_reason: str | None = None
    has_tool_calls: bool = False


async def call_llm(
    messages: list[dict],
    tool_schemas: list[dict],
    system_prompt: str,
    context: Any,
    stream_kwargs: dict[str, Any],
) -> LLMResult:
    """调用 LLM 流式接口，收集 tool_calls / usage / finish_reason。"""
    current_tool_calls: dict[int, dict] = {}
    has_tool_calls = False
    finish_reason = None

    try:
        async for event in create_stream(
            messages,
            tool_schemas,
            system_prompt,
            model=context.settings.model,
            api_key=context.settings.api_key,
            base_url=context.settings.base_url,
            client=getattr(context, "llm_client", None),
            **stream_kwargs,
        ):
            if event.type == "tool_calls":
                has_tool_calls = True
                idx = event.data.get("index", 0)
                if idx not in current_tool_calls:
                    current_tool_calls[idx] = {
                        "id": event.data["id"],
                        "name": event.data["name"],
                        "arguments": "",
                    }
                current_tool_calls[idx]["arguments"] += event.data.get("arguments") or ""

            if event.type == "usage":
                svc = getattr(context, "cost_tracker_service", None)
                if svc is not None:
                    svc.record(
                        input_tokens=event.data.get("input_tokens", 0),
                        output_tokens=event.data.get("output_tokens", 0),
                        model=event.data.get("model"),
                        duration_ms=event.data.get("duration_ms", 0),
                    )

            if event.type == "finish_reason":
                finish_reason = event.data.get("reason")

        save_cache_safe_params(build_cache_safe_params(
            system_prompt=system_prompt,
            tools=tool_schemas,
            messages=messages,
            model=context.settings.model if hasattr(context, "settings") else "",
            base_url=context.settings.base_url if hasattr(context, "settings") else "",
            api_key=context.settings.api_key if hasattr(context, "settings") else "",
            prefix_count=2,
        ))
    except Exception as e:
        error_str = str(e).lower()
        if any(kw in error_str for kw in _OVERFLOW_KEYWORDS):
            try:
                from src.services.context_collapse import is_context_collapse_enabled
                if is_context_collapse_enabled():
                    raise CollapseRetryError from e
            except ImportError:
                pass
            raise CompactRetryError from e
        raise

    return LLMResult(
        tool_calls=current_tool_calls,
        finish_reason=finish_reason,
        has_tool_calls=has_tool_calls,
    )
