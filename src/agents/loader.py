from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agents.agent_definition import AgentDefinition, AgentType

try:
    import yaml
except ImportError:
    yaml = None


class AgentLoader:
    def __init__(self, search_paths: list[Path] | None = None):
        self._search_paths = search_paths or []
        self._loaded: dict[str, AgentDefinition] = {}

    def add_search_path(self, path: Path) -> None:
        if path not in self._search_paths:
            self._search_paths.append(path)

    def load_all(self) -> dict[str, AgentDefinition]:
        for path in self._search_paths:
            if path.is_dir():
                self._load_from_directory(path)
        return dict(self._loaded)

    def get(self, name: str) -> AgentDefinition | None:
        return self._loaded.get(name)

    def get_all(self) -> dict[str, AgentDefinition]:
        return dict(self._loaded)

    def register(self, definition: AgentDefinition) -> None:
        self._loaded[definition.name] = definition

    def _load_from_directory(self, directory: Path) -> None:
        if not directory.is_dir():
            return

        for yaml_file in sorted(directory.glob("*.yml")):
            self._load_yaml_file(yaml_file)
        for yaml_file in sorted(directory.glob("*.yaml")):
            self._load_yaml_file(yaml_file)

    def _load_yaml_file(self, filepath: Path) -> None:
        if yaml is None:
            return

        try:
            content = filepath.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return
            definition = self._parse_definition(data, filepath.stem)
            if definition:
                self._loaded[definition.name] = definition
        except (OSError, ValueError, KeyError):
            pass

    def _parse_definition(self, data: dict[str, Any], fallback_name: str) -> AgentDefinition | None:
        name = data.get("name", fallback_name)
        agent_type_str = data.get("agentType", data.get("agent_type", "custom"))
        try:
            agent_type = AgentType(agent_type_str)
        except ValueError:
            agent_type = AgentType.CUSTOM

        return AgentDefinition(
            name=name,
            agent_type=agent_type,
            when_to_use=data.get("whenToUse", data.get("when_to_use", "")),
            description=data.get("description", ""),
            tools=data.get("tools", []),
            disallowed_tools=data.get("disallowedTools", data.get("disallowed_tools", [])),
            model=data.get("model"),
            effort=data.get("effort", "medium"),
            permission_mode=data.get("permissionMode", data.get("permission_mode", "default")),
            max_turns=data.get("maxTurns", data.get("max_turns", 50)),
            memory=data.get("memory", False),
            memory_scope=data.get("memoryScope", data.get("memory_scope", "project")),
            isolation=data.get("isolation", False),
            system_prompt=data.get("systemPrompt", data.get("system_prompt", "")),
            system_prompt_append=data.get("systemPromptAppend", data.get("system_prompt_append", True)),
            metadata=data.get("metadata", {}),
        )
