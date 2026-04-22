from __future__ import annotations

import hashlib
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentType(str, Enum):
    SUBAGENT = "subagent"
    TEAMMATE = "teammate"


@dataclass
class SubagentContext:
    agent_id: str
    parent_session_id: str
    subagent_name: str
    is_built_in: bool = False
    agent_type: str = "subagent"


@dataclass
class TeammateAgentContext:
    agent_id: str
    agent_name: str
    team_name: str
    agent_color: str = ""
    plan_mode_required: bool = False
    agent_type: str = "teammate"


AgentContext = SubagentContext | TeammateAgentContext | None

_current_agent_context: ContextVar[AgentContext] = ContextVar("agent_context", default=None)
_current_agent_state: ContextVar[dict[str, Any]] = ContextVar("agent_state", default={})


def get_agent_context() -> AgentContext:
    return _current_agent_context.get()


def set_agent_context(ctx: AgentContext) -> None:
    _current_agent_context.set(ctx)


def is_subagent_context() -> bool:
    ctx = get_agent_context()
    return ctx is not None and getattr(ctx, "agent_type", None) == "subagent"


def is_teammate_context() -> bool:
    ctx = get_agent_context()
    return ctx is not None and getattr(ctx, "agent_type", None) == "teammate"


def get_agent_state() -> dict[str, Any]:
    return _current_agent_state.get()


def set_agent_state(state: dict[str, Any]) -> None:
    _current_agent_state.set(state)


def generate_agent_id(name: str, team: str = "main") -> str:
    raw = f"{name}@{team}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def create_isolated_agent_state(
    parent_state: dict[str, Any] | None = None,
    share_read_files: bool = True,
    share_abort: bool = False,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "read_files": set(),
        "denial_tracking": {},
        "file_history": [],
        "checkpoint_count": 0,
    }
    if parent_state is not None:
        if share_read_files:
            state["read_files"] = set(parent_state.get("read_files", set()))
        if share_abort:
            state["abort_event"] = parent_state.get("abort_event")
    return state


class AgentContextManager:
    def __init__(self):
        self._token_ctx = None
        self._token_state = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._token_ctx is not None:
            _current_agent_context.reset(self._token_ctx)
        if self._token_state is not None:
            _current_agent_state.reset(self._token_state)

    def bind(self, ctx: AgentContext, state: dict[str, Any] | None = None) -> AgentContextManager:
        self._token_ctx = _current_agent_context.set(ctx)
        if state is not None:
            self._token_state = _current_agent_state.set(state)
        return self
