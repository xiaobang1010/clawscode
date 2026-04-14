from __future__ import annotations

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
