from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.agents.agent_definition import AgentDefinition
from src.plugins.types import LoadedPlugin

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


class PluginAgentLoader:
    def __init__(self) -> None:
        self._loaded: dict[str, AgentDefinition] = {}

    def load(self, plugin: LoadedPlugin) -> list[str]:
        agents_dir = plugin.path / "agents"
        if not agents_dir.is_dir():
            return []

        loaded: list[str] = []
        for yaml_file in sorted(agents_dir.glob("*.yml")):
            name = self._load_agent_file(yaml_file, plugin.name)
            if name:
                loaded.append(name)
        for yaml_file in sorted(agents_dir.glob("*.yaml")):
            name = self._load_agent_file(yaml_file, plugin.name)
            if name:
                loaded.append(name)

        plugin.loaded_agents = loaded
        return loaded

    def unload(self, plugin: LoadedPlugin) -> None:
        for agent_name in plugin.loaded_agents:
            self._loaded.pop(f"{plugin.name}:{agent_name}", None)
        plugin.loaded_agents = []

    def get(self, plugin_name: str, agent_name: str) -> AgentDefinition | None:
        return self._loaded.get(f"{plugin_name}:{agent_name}")

    def get_all(self) -> dict[str, AgentDefinition]:
        return dict(self._loaded)

    def _load_agent_file(self, filepath: Path, plugin_name: str) -> str | None:
        if yaml is None:
            return None

        try:
            content = filepath.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return None

            from src.agents.agent_definition import AgentType

            name = data.get("name", filepath.stem)
            agent_type_str = data.get("agentType", data.get("agent_type", "custom"))
            try:
                agent_type = AgentType(agent_type_str)
            except ValueError:
                agent_type = AgentType.CUSTOM

            definition = AgentDefinition(
                name=f"{plugin_name}:{name}",
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
                metadata={"plugin": plugin_name, **data.get("metadata", {})},
            )

            self._loaded[f"{plugin_name}:{name}"] = definition
            logger.debug(
                "Loaded agent '%s' from plugin '%s'", name, plugin_name
            )
            return name
        except (OSError, ValueError, KeyError) as e:
            logger.warning(
                "Failed to load agent '%s' from plugin '%s': %s",
                filepath,
                plugin_name,
                e,
            )
            return None
