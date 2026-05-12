from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Transition(Enum):
    NEXT_TURN = "next_turn"
    COMPLETED = "completed"
    MAX_OUTPUT_TOKENS_RECOVERY = "max_output_tokens_recovery"
    REACTIVE_COMPACT_RETRY = "reactive_compact_retry"
    COLLAPSE_DRAIN_RETRY = "collapse_drain_retry"
    STOP_HOOK_BLOCKING = "stop_hook_blocking"
    ABORTED = "aborted"


MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3


@dataclass
class QueryState:
    messages: list[dict] = field(default_factory=list)
    transition: Transition = Transition.NEXT_TURN
    max_output_tokens_recovery_count: int = 0
    stop_hook_active: bool = False
    last_compact_tokens_before: int = 0
    last_compact_tokens_after: int = 0
    active_skill_tools: list[str] | None = None
    has_attempted_reactive_compact: bool = False


@dataclass
class QueryEngineConfig:
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 128000
    max_turns: int = 100
