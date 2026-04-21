from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HookEvent(str, Enum):
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    STOP = "Stop"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    TASK_COMPLETED = "TaskCompleted"
    TEAMMATE_IDLE = "TeammateIdle"
    NOTIFICATION = "Notification"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"


class HookType(str, Enum):
    PROMPT = "prompt"
    AGENT = "agent"
    HTTP = "http"


@dataclass
class HookResult:
    output: str = ""
    error: str | None = None
    should_block: bool = False
    prevent_continuation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookDefinition:
    name: str
    event: HookEvent
    hook_type: HookType
    command: str = ""
    url: str = ""
    agent_type: str = ""
    timeout: float = 30.0
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "event": self.event.value,
            "hook_type": self.hook_type.value,
            "command": self.command,
            "url": self.url,
            "agent_type": self.agent_type,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


@dataclass
class HookContext:
    event: HookEvent
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    tool_output: str = ""
    session_id: str = ""
    messages: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
