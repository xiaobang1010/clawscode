from __future__ import annotations

from dataclasses import dataclass, field


class FallbackTriggeredError(Exception):
    def __init__(self, message: str, original_error: Exception | None = None, fallback_model: str = ""):
        super().__init__(message)
        self.original_error = original_error
        self.fallback_model = fallback_model


@dataclass
class FallbackModelConfig:
    primary_model: str
    fallback_models: list[str] = field(default_factory=list)
    max_retries: int = 1


_OVERLOAD_KEYWORDS = (
    "overloaded",
    "overload",
    "capacity",
    "rate_limit",
    "rate limit",
    "too many requests",
    "503",
    "529",
    "server_error",
    "internal server error",
    "service unavailable",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection error",
    "connection refused",
)


def should_trigger_fallback(error: Exception) -> bool:
    error_str = str(error).lower()
    return any(kw in error_str for kw in _OVERLOAD_KEYWORDS)


def complete_missing_tool_results(messages: list[dict]) -> list[dict]:
    result = list(messages)
    i = 0
    while i < len(result):
        msg = result[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_ids = {tc.get("id") for tc in msg["tool_calls"]}

            next_idx = i + 1
            provided_ids = set()
            while next_idx < len(result) and result[next_idx].get("role") == "tool":
                provided_ids.add(result[next_idx].get("tool_call_id", ""))
                next_idx += 1

            missing_ids = tool_ids - provided_ids
            for tid in missing_ids:
                tool_name = ""
                for tc in msg["tool_calls"]:
                    if tc.get("id") == tid:
                        tool_name = tc.get("function", {}).get("name", "")
                        break

                placeholder = {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": f"[工具 '{tool_name}' 因模型切换未返回结果，请重试]",
                }
                result.insert(next_idx, placeholder)
                next_idx += 1

        i += 1

    return result
