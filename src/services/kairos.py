from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class KairosEvent:
    timestamp: str
    event_type: str
    correlation_id: str
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class KairosLogger:
    def __init__(self, cwd: Path | None = None):
        self._cwd = cwd or Path.cwd()
        self._events: list[KairosEvent] = []
        self._correlation_id = ""
        self._start_times: dict[str, float] = {}

    def set_correlation_id(self, cid: str) -> None:
        self._correlation_id = cid

    def start_timer(self, key: str) -> None:
        self._start_times[key] = time.monotonic()

    def log_event(self, event_type: str, metadata: dict[str, Any] | None = None, timer_key: str = "") -> None:
        duration = 0.0
        if timer_key and timer_key in self._start_times:
            duration = (time.monotonic() - self._start_times.pop(timer_key)) * 1000
        event = KairosEvent(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            correlation_id=self._correlation_id,
            duration_ms=round(duration, 2),
            metadata=metadata or {},
        )
        self._events.append(event)

    def flush(self) -> None:
        if not self._events:
            return
        kairos_dir = self._cwd / ".clawscode" / "kairos"
        kairos_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = kairos_dir / f"{date_str}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps({
                    "timestamp": event.timestamp,
                    "event_type": event.event_type,
                    "correlation_id": event.correlation_id,
                    "duration_ms": event.duration_ms,
                    "metadata": event.metadata,
                }, ensure_ascii=False) + "\n")
        self._events.clear()

    def get_event_count(self) -> int:
        return len(self._events)
