from __future__ import annotations

import os
from dataclasses import dataclass, field

from src.services.token_counter import count_tokens


@dataclass
class ToolResultBudget:
    tool_name: str
    max_chars: int
    current_chars: int = 0
    replacement_count: int = 0


@dataclass
class QueryBudget:
    max_tokens: int
    system_tokens: int = 0
    tool_result_tokens: int = 0
    conversation_tokens: int = 0
    reserved_tokens: int = 4096

    @property
    def used_tokens(self) -> int:
        return self.system_tokens + self.tool_result_tokens + self.conversation_tokens

    @property
    def available_tokens(self) -> int:
        return max(0, self.max_tokens - self.used_tokens - self.reserved_tokens)

    @property
    def is_over_budget(self) -> bool:
        return self.used_tokens + self.reserved_tokens > self.max_tokens


class TokenBudgetManager:
    def __init__(self, max_tokens: int = 128000):
        self._max_tokens = max_tokens
        self._tool_budgets: dict[str, ToolResultBudget] = {}
        self._default_max_chars = 25000
        self._streaming_tokens: int = 0

    def set_tool_budget(self, tool_name: str, max_chars: int) -> None:
        self._tool_budgets[tool_name] = ToolResultBudget(
            tool_name=tool_name, max_chars=max_chars,
        )

    def get_tool_max_chars(self, tool_name: str) -> int:
        if tool_name in self._tool_budgets:
            return self._tool_budgets[tool_name].max_chars
        return self._default_max_chars

    def record_tool_result(self, tool_name: str, chars: int) -> None:
        if tool_name not in self._tool_budgets:
            self._tool_budgets[tool_name] = ToolResultBudget(
                tool_name=tool_name, max_chars=self._default_max_chars,
            )
        self._tool_budgets[tool_name].current_chars += chars
        self._tool_budgets[tool_name].replacement_count += 1

    def compute_query_budget(
        self,
        system_prompt: str,
        messages: list[dict],
    ) -> QueryBudget:
        system_tokens = count_tokens([{"role": "system", "content": system_prompt}])
        conversation_tokens = count_tokens(messages)

        tool_result_tokens = 0
        for msg in messages:
            if msg.get("role") == "tool":
                tool_result_tokens += count_tokens([msg])

        return QueryBudget(
            max_tokens=self._max_tokens,
            system_tokens=system_tokens,
            tool_result_tokens=tool_result_tokens,
            conversation_tokens=conversation_tokens,
        )

    def should_compact(self, messages: list[dict], threshold_ratio: float = 0.8) -> bool:
        used = count_tokens(messages)
        return used > self._max_tokens * threshold_ratio

    def update_streaming_tokens(self, delta: int) -> None:
        self._streaming_tokens += delta

    def get_streaming_tokens(self) -> int:
        return self._streaming_tokens

    def reset_streaming_tokens(self) -> None:
        self._streaming_tokens = 0

    def get_budget_summary(self) -> str:
        total_tool_chars = sum(b.current_chars for b in self._tool_budgets.values())
        return (
            f"Token 预算: {self._max_tokens} | "
            f"工具结果: {total_tool_chars} chars ({len(self._tool_budgets)} 工具) | "
            f"流式: {self._streaming_tokens} tokens"
        )


MODEL_CONTEXT_WINDOW_MAP: dict[str, int] = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    "claude-3.5-sonnet": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-sonnet-4": 200000,
    "ZhipuAI/GLM-5": 128000,
    "deepseek-chat": 64000,
    "deepseek-coder": 16000,
    "qwen-max": 32000,
    "qwen-plus": 131072,
    "qwen-turbo": 131072,
    "gemini-1.5-pro": 2097152,
    "gemini-1.5-flash": 1048576,
}

MODEL_MAX_OUTPUT_TOKENS_MAP: dict[str, tuple[int, int]] = {
    "claude-3-opus": (4096, 4096),
    "claude-3-sonnet": (8192, 8192),
    "claude-3-haiku": (8192, 8192),
    "claude-sonnet-4": (16384, 16384),
    "claude-opus-4": (16384, 32768),
    "gpt-4": (8192, 8192),
    "gpt-4o": (16384, 16384),
    "deepseek-chat": (8192, 8192),
}


def get_model_max_output_tokens(model: str) -> tuple[int, int]:
    if model in MODEL_MAX_OUTPUT_TOKENS_MAP:
        return MODEL_MAX_OUTPUT_TOKENS_MAP[model]
    for prefix, tokens in MODEL_MAX_OUTPUT_TOKENS_MAP.items():
        if model.startswith(prefix):
            return tokens
    return (8192, 8192)


def infer_context_window(model: str, default: int = 128000) -> int:
    env_value = os.environ.get("CLAWSCODE_CONTEXT_WINDOW")
    if env_value:
        return int(env_value)
    if not model:
        return default
    window = default
    if model in MODEL_CONTEXT_WINDOW_MAP:
        window = MODEL_CONTEXT_WINDOW_MAP[model]
    else:
        for prefix, w in MODEL_CONTEXT_WINDOW_MAP.items():
            if model.startswith(prefix):
                window = w
                break
    pct_override = os.environ.get("CLAWSCODE_AUTOCOMPACT_PCT_OVERRIDE")
    if pct_override:
        return int(window * float(pct_override))
    return window


def get_effective_context_window_size(model: str, default: int = 128000) -> int:
    context_window = infer_context_window(model, default)
    _, max_output = get_model_max_output_tokens(model)
    return context_window - min(max_output, 20000)


def get_auto_compact_threshold(model: str, default: int = 128000) -> int:
    effective_window = get_effective_context_window_size(model, default)
    return effective_window - 13000


def should_auto_compact(messages: list[dict], model: str, query_source: str = "", default: int = 128000) -> bool:
    if query_source in ("session_memory", "compact", "marble_origami"):
        return False
    threshold = get_auto_compact_threshold(model, default)
    used = count_tokens(messages)
    return used >= threshold


class DiminishingReturnDetector:
    def __init__(self, window_size: int = 5, threshold: float = 0.3):
        self._history: list[int] = []
        self._window_size = window_size
        self._threshold = threshold

    def record(self, saved_tokens: int) -> None:
        self._history.append(saved_tokens)
        if len(self._history) > self._window_size:
            self._history = self._history[-self._window_size:]

    def is_diminishing(self) -> bool:
        if len(self._history) < 3:
            return False
        recent = self._history[-3:]
        for i in range(len(recent) - 1):
            if recent[i] == 0:
                return True
            reduction = (recent[i] - recent[i + 1]) / recent[i]
            if reduction < self._threshold:
                return False
        return True


import re as _re


def parse_token_budget(text: str) -> int | None:
    if not text:
        return None
    match = _re.match(r'^\+?(\d+(?:\.\d+)?)\s*([kKmMbB]?)[tT]?$',
                       text.strip())
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {'k': 1000, 'm': 1_000_000, 'b': 1_000_000_000}
    multiplier = multipliers.get(unit, 1)
    return int(value * multiplier)


def find_token_budget_positions(text: str) -> list[tuple[int, int, int]]:
    pattern = r'\+?\d+(?:\.\d+)?\s*[kKmMbB]?[tT]?'
    results: list[tuple[int, int, int]] = []
    for match in _re.finditer(pattern, text):
        value = parse_token_budget(match.group())
        if value is not None:
            results.append((match.start(), match.end(), value))
    return results


def get_budget_continuation_message(
    pct: float,
    turn_tokens: int,
    budget: int,
) -> str:
    remaining = budget - int(budget * pct)
    return (
        f"已使用约 {pct:.0%} 的 token 预算（本轮 {turn_tokens:,} tokens，"
        f"剩余约 {remaining:,} tokens）。继续工作，不要总结。"
        f"完成当前任务的所有必要步骤。"
    )


class BudgetTracker:
    def __init__(self, total_budget: int):
        self.total_budget = total_budget
        self.used_tokens = 0
        self._turn_tokens: list[int] = []

    def update(self, used: int) -> None:
        self.used_tokens += used

    def record_turn(self, turn_tokens: int) -> None:
        self._turn_tokens.append(turn_tokens)
        self.update(turn_tokens)

    @property
    def completion_pct(self) -> float:
        if self.total_budget <= 0:
            return 1.0
        return min(1.0, self.used_tokens / self.total_budget)

    def is_complete(self) -> bool:
        return self.completion_pct >= 0.9

    def should_continue(self) -> bool:
        if self.is_complete():
            return False
        if len(self._turn_tokens) >= 3:
            recent = self._turn_tokens[-3:]
            if all(t < 100 for t in recent):
                return False
        return True


def check_token_budget(tracker: BudgetTracker) -> dict[str, Any]:
    should_stop = tracker.is_complete()
    reason = ""
    continuation_message = ""

    if should_stop:
        reason = "budget_exhausted"
    elif not tracker.should_continue():
        should_stop = True
        reason = "diminishing_returns"
    elif tracker.completion_pct >= 0.75:
        continuation_message = get_budget_continuation_message(
            tracker.completion_pct,
            tracker._turn_tokens[-1] if tracker._turn_tokens else 0,
            tracker.total_budget,
        )

    return {
        "should_stop": should_stop,
        "reason": reason,
        "continuation_message": continuation_message,
        "completion_pct": tracker.completion_pct,
    }
