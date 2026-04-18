from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PluginState(str, Enum):
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    license: str = ""
    requires: list[str] = field(default_factory=list)
    provides_commands: list[str] = field(default_factory=list)
    provides_agents: list[str] = field(default_factory=list)
    provides_skills: list[str] = field(default_factory=list)
    provides_hooks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "license": self.license,
            "requires": self.requires,
            "provides_commands": self.provides_commands,
            "provides_agents": self.provides_agents,
            "provides_skills": self.provides_skills,
            "provides_hooks": self.provides_hooks,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            homepage=data.get("homepage", ""),
            license=data.get("license", ""),
            requires=data.get("requires", []),
            provides_commands=data.get("providesCommands", data.get("provides_commands", [])),
            provides_agents=data.get("providesAgents", data.get("provides_agents", [])),
            provides_skills=data.get("providesSkills", data.get("provides_skills", [])),
            provides_hooks=data.get("providesHooks", data.get("provides_hooks", [])),
            metadata=data.get("metadata", {}),
        )


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    path: Path
    state: PluginState = PluginState.DISCOVERED
    error: str | None = None
    loaded_commands: list[str] = field(default_factory=list)
    loaded_agents: list[str] = field(default_factory=list)
    loaded_skills: list[str] = field(default_factory=list)
    loaded_hooks: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def is_enabled(self) -> bool:
        return self.state == PluginState.ENABLED

    @property
    def is_loaded(self) -> bool:
        return self.state in (PluginState.LOADED, PluginState.ENABLED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.manifest.name,
            "version": self.manifest.version,
            "description": self.manifest.description,
            "path": str(self.path),
            "state": self.state.value,
            "error": self.error,
            "loaded_commands": self.loaded_commands,
            "loaded_agents": self.loaded_agents,
            "loaded_skills": self.loaded_skills,
            "loaded_hooks": self.loaded_hooks,
        }
