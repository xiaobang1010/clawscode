from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentType(str, Enum):
    GENERAL = "general"
    EXPLORE = "explore"
    PLAN = "plan"
    VERIFICATION = "verification"
    CUSTOM = "custom"


@dataclass
class AgentDefinition:
    name: str
    agent_type: AgentType = AgentType.GENERAL
    when_to_use: str = ""
    description: str = ""
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    effort: str = "medium"
    permission_mode: str = "default"
    max_turns: int = 50
    memory: bool = False
    memory_scope: str = "project"
    isolation: bool = False
    system_prompt: str = ""
    system_prompt_append: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_allowed_tools(self) -> list[str] | None:
        if self.tools:
            return self.tools
        return None

    def get_disallowed_tools(self) -> list[str]:
        return self.disallowed_tools

    def get_model_override(self) -> str | None:
        return self.model

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agent_type": self.agent_type.value,
            "when_to_use": self.when_to_use,
            "description": self.description,
            "tools": self.tools,
            "disallowed_tools": self.disallowed_tools,
            "model": self.model,
            "effort": self.effort,
            "permission_mode": self.permission_mode,
            "max_turns": self.max_turns,
            "memory": self.memory,
            "memory_scope": self.memory_scope,
            "isolation": self.isolation,
        }
