from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SkillDefinition:
    name: str
    description: str
    when_to_use: str
    allowed_tools: list[str]
    get_prompt_for_command: str
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    hooks: dict[str, list[dict]] | None = None
    context: str = "inline"
    skill_dir: str | None = None
    agent: str | None = None
    files: list[str] | None = None
    is_enabled: Callable[[], bool] | None = None
    disable_model_invocation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "when_to_use": self.when_to_use,
            "allowed_tools": self.allowed_tools,
            "get_prompt_for_command": self.get_prompt_for_command,
            "aliases": self.aliases,
            "metadata": self.metadata,
            "context": self.context,
            "skill_dir": self.skill_dir,
            "agent": self.agent,
            "files": self.files,
            "disable_model_invocation": self.disable_model_invocation,
        }
