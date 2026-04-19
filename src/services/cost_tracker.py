from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "default": {"input": 0.003, "output": 0.015},
}

CLAWSCODE_DIR_NAME = ".clawscode"
COST_FILE_NAME = "cost_history.json"


@dataclass
class CostEntry:
    timestamp: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: float


@dataclass
class CostSummary:
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_api_calls: int = 0
    total_duration_ms: float = 0.0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def format(self) -> str:
        lines = [
            f"输入 Tokens: {self.total_input_tokens:,}",
            f"输出 Tokens: {self.total_output_tokens:,}",
            f"总费用: ${self.total_cost_usd:.4f}",
            f"API 调用: {self.total_api_calls}",
            f"总耗时: {self.total_duration_ms:.0f}ms",
        ]
        if self.by_model:
            lines.append("\n按模型统计:")
            for model, stats in self.by_model.items():
                lines.append(f"  {model}: {stats.get('cost', 0):.4f} USD ({stats.get('calls', 0)} calls)")
        return "\n".join(lines)


class CostTrackerService:
    def __init__(self, model: str = "default", home: Path | None = None, custom_pricing: dict[str, dict[str, float]] | None = None):
        self._model = model
        self._home = home or Path.home()
        self._cost_file = self._home / CLAWSCODE_DIR_NAME / COST_FILE_NAME
        self._entries: list[CostEntry] = []
        self._session_summary = CostSummary()
        self._pricing = {**MODEL_PRICING, **(custom_pricing or {})}

    @property
    def session_summary(self) -> CostSummary:
        return self._session_summary

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str | None = None,
        duration_ms: float = 0.0,
    ) -> CostEntry:
        model = model or self._model
        pricing = self._pricing.get(model, self._pricing["default"])
        cost = (input_tokens / 1000.0 * pricing["input"]) + (output_tokens / 1000.0 * pricing["output"])

        entry = CostEntry(
            timestamp=datetime.now().isoformat(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
        )

        self._entries.append(entry)
        self._update_summary(entry)
        self._persist_entry(entry)

        return entry

    def get_session_summary(self) -> CostSummary:
        return self._session_summary

    def get_historical_summary(self) -> CostSummary:
        entries = self._load_historical_entries()
        return self._compute_summary(entries)

    def format_session_summary(self) -> str:
        return self._session_summary.format()

    def _update_summary(self, entry: CostEntry) -> None:
        self._session_summary.total_input_tokens += entry.input_tokens
        self._session_summary.total_output_tokens += entry.output_tokens
        self._session_summary.total_cost_usd += entry.cost_usd
        self._session_summary.total_api_calls += 1
        self._session_summary.total_duration_ms += entry.duration_ms

        model = entry.model
        if model not in self._session_summary.by_model:
            self._session_summary.by_model[model] = {"cost": 0.0, "calls": 0, "tokens": 0}
        self._session_summary.by_model[model]["cost"] += entry.cost_usd
        self._session_summary.by_model[model]["calls"] += 1
        self._session_summary.by_model[model]["tokens"] += entry.input_tokens + entry.output_tokens

    def _persist_entry(self, entry: CostEntry) -> None:
        try:
            self._cost_file.parent.mkdir(parents=True, exist_ok=True)

            existing = []
            if self._cost_file.exists():
                content = self._cost_file.read_text(encoding="utf-8")
                existing = json.loads(content)
                if not isinstance(existing, list):
                    existing = []
            else:
                existing = []

            existing.append({
                "timestamp": entry.timestamp,
                "model": entry.model,
                "input_tokens": entry.input_tokens,
                "output_tokens": entry.output_tokens,
                "cost_usd": entry.cost_usd,
                "duration_ms": entry.duration_ms,
            })

            self._cost_file.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except (OSError, json.JSONDecodeError):
            pass

    def _load_historical_entries(self) -> list[CostEntry]:
        entries = []
        try:
            if self._cost_file.exists():
                content = self._cost_file.read_text(encoding="utf-8")
                data = json.loads(content)
                for item in data:
                    entries.append(CostEntry(
                        timestamp=item.get("timestamp", ""),
                        model=item.get("model", ""),
                        input_tokens=item.get("input_tokens", 0),
                        output_tokens=item.get("output_tokens", 0),
                        cost_usd=item.get("cost_usd", 0.0),
                        duration_ms=item.get("duration_ms", 0.0),
                    ))
        except (OSError, json.JSONDecodeError):
            pass
        return entries

    def _compute_summary(self, entries: list[CostEntry]) -> CostSummary:
        summary = CostSummary()
        for entry in entries:
            summary.total_input_tokens += entry.input_tokens
            summary.total_output_tokens += entry.output_tokens
            summary.total_cost_usd += entry.cost_usd
            summary.total_api_calls += 1
            summary.total_duration_ms += entry.duration_ms

            if entry.model not in summary.by_model:
                summary.by_model[entry.model] = {"cost": 0.0, "calls": 0, "tokens": 0}
            summary.by_model[entry.model]["cost"] += entry.cost_usd
            summary.by_model[entry.model]["calls"] += 1
            summary.by_model[entry.model]["tokens"] += entry.input_tokens + entry.output_tokens

        return summary
