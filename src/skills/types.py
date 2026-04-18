from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillDefinition:
    name: str
    description: str
    when_to_use: str
    allowed_tools: list[str]
    get_prompt_for_command: str
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "when_to_use": self.when_to_use,
            "allowed_tools": self.allowed_tools,
            "get_prompt_for_command": self.get_prompt_for_command,
            "aliases": self.aliases,
            "metadata": self.metadata,
        }
