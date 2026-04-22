from __future__ import annotations

import hashlib
import uuid
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


@dataclass
class FileStateCache:
    _cache: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def keys(self) -> list[str]:
        return list(self._cache.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __len__(self) -> int:
        return len(self._cache)


def clone_file_state_cache(cache: FileStateCache | None) -> FileStateCache:
    if cache is None:
        return FileStateCache()
    return FileStateCache(_cache=dict(cache._cache))


@dataclass
class DenialTrackingState:
    denials: dict[str, int] = field(default_factory=dict)
    total_denials: int = 0

    def record_denial(self, tool_name: str) -> None:
        self.denials[tool_name] = self.denials.get(tool_name, 0) + 1
        self.total_denials += 1

    def get_denial_count(self, tool_name: str) -> int:
        return self.denials.get(tool_name, 0)


def create_denial_tracking_state() -> DenialTrackingState:
    return DenialTrackingState()


@dataclass
class ContentReplacementState:
    replacements: list[dict[str, Any]] = field(default_factory=list)

    def record(self, original_chars: int, replacement_chars: int, tool_name: str, message_index: int) -> None:
        self.replacements.append({
            "original_chars": original_chars,
            "replacement_chars": replacement_chars,
            "tool_name": tool_name,
            "message_index": message_index,
        })

    def get_total_saved(self) -> int:
        return sum(r["original_chars"] - r["replacement_chars"] for r in self.replacements)


def clone_content_replacement_state(state: ContentReplacementState | None) -> ContentReplacementState | None:
    if state is None:
        return None
    return ContentReplacementState(replacements=list(state.replacements))


@dataclass
class QueryTracking:
    chain_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    depth: int = 0


def create_query_tracking(parent_depth: int = -1) -> QueryTracking:
    return QueryTracking(depth=parent_depth + 1)


@dataclass
class SubagentContextOverrides:
    options: dict[str, Any] | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    messages: list[dict] | None = None
    read_file_state: FileStateCache | None = None
    abort_controller: Any | None = None
    get_app_state: Any | None = None
    share_set_app_state: bool = False
    share_set_response_length: bool = False
    share_abort_controller: bool = False
    critical_system_reminder: str | None = None
    require_can_use_tool: bool = False
    content_replacement_state: ContentReplacementState | None = None


@dataclass
class ToolUseContext:
    read_file_state: FileStateCache
    nested_memory_attachment_triggers: set[str] = field(default_factory=set)
    loaded_nested_memory_paths: set[str] = field(default_factory=set)
    dynamic_skill_dir_triggers: set[str] = field(default_factory=set)
    discovered_skill_names: set[str] = field(default_factory=set)
    tool_decisions: dict[str, Any] | None = None
    content_replacement_state: ContentReplacementState | None = None
    abort_controller: Any | None = None
    get_app_state: Any | None = None
    set_app_state: Any = lambda: None
    set_app_state_for_tasks: Any | None = None
    local_denial_tracking: DenialTrackingState = field(default_factory=create_denial_tracking_state)
    set_in_progress_tool_use_ids: Any = lambda: None
    set_response_length: Any = lambda: None
    push_api_metrics_entry: Any | None = None
    update_file_history_state: Any = lambda: None
    update_attribution_state: Any = lambda: None
    add_notification: Any | None = None
    set_tool_jsx: Any | None = None
    set_stream_mode: Any | None = None
    set_sdk_status: Any | None = None
    open_message_selector: Any | None = None
    options: dict[str, Any] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_type: str | None = None
    query_tracking: QueryTracking = field(default_factory=QueryTracking)
    file_reading_limits: dict[str, Any] = field(default_factory=dict)
    user_modified: bool = False
    critical_system_reminder_experimental: str | None = None
    require_can_use_tool: bool = False


def create_subagent_context(
    parent_context: ToolUseContext,
    overrides: SubagentContextOverrides | None = None,
) -> ToolUseContext:
    if overrides is None:
        overrides = SubagentContextOverrides()

    abort_controller = overrides.abort_controller
    if abort_controller is None:
        if overrides.share_abort_controller:
            abort_controller = parent_context.abort_controller
        else:
            import asyncio
            parent_abort = parent_context.abort_controller
            if parent_abort is not None:
                child_abort = asyncio.Event()
                abort_controller = child_abort
            else:
                abort_controller = None

    get_app_state = overrides.get_app_state
    if get_app_state is None:
        if overrides.share_abort_controller:
            get_app_state = parent_context.get_app_state
        else:
            def _wrapped_get_app_state():
                state = parent_context.get_app_state() if parent_context.get_app_state else {}
                if isinstance(state, dict) and "tool_permission_context" in state:
                    state["tool_permission_context"]["should_avoid_permission_prompts"] = True
                return state
            get_app_state = _wrapped_get_app_state

    return ToolUseContext(
        read_file_state=clone_file_state_cache(
            overrides.read_file_state if overrides.read_file_state else parent_context.read_file_state
        ),
        nested_memory_attachment_triggers=set(),
        loaded_nested_memory_paths=set(),
        dynamic_skill_dir_triggers=set(),
        discovered_skill_names=set(),
        tool_decisions=None,
        content_replacement_state=(
            overrides.content_replacement_state
            if overrides.content_replacement_state
            else (clone_content_replacement_state(parent_context.content_replacement_state)
                  if parent_context.content_replacement_state else None)
        ),
        abort_controller=abort_controller,
        get_app_state=get_app_state,
        set_app_state=parent_context.set_app_state if overrides.share_set_app_state else lambda: None,
        set_app_state_for_tasks=parent_context.set_app_state_for_tasks or parent_context.set_app_state,
        local_denial_tracking=(
            parent_context.local_denial_tracking
            if overrides.share_set_app_state
            else create_denial_tracking_state()
        ),
        set_in_progress_tool_use_ids=lambda: None,
        set_response_length=(
            parent_context.set_response_length
            if overrides.share_set_response_length
            else lambda: None
        ),
        push_api_metrics_entry=(
            parent_context.push_api_metrics_entry
            if overrides.share_set_response_length
            else None
        ),
        update_file_history_state=lambda: None,
        update_attribution_state=parent_context.update_attribution_state,
        add_notification=None,
        set_tool_jsx=None,
        set_stream_mode=None,
        set_sdk_status=None,
        open_message_selector=None,
        options=overrides.options if overrides.options else parent_context.options,
        messages=overrides.messages if overrides.messages else parent_context.messages,
        agent_id=overrides.agent_id if overrides.agent_id else str(uuid.uuid4())[:8],
        agent_type=overrides.agent_type,
        query_tracking=create_query_tracking(parent_context.query_tracking.depth),
        file_reading_limits=parent_context.file_reading_limits,
        user_modified=parent_context.user_modified,
        critical_system_reminder_experimental=overrides.critical_system_reminder,
        require_can_use_tool=overrides.require_can_use_tool,
    )


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
