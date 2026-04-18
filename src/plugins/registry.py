from __future__ import annotations

import logging
from typing import Any

from src.plugins.types import LoadedPlugin, PluginState

logger = logging.getLogger(__name__)


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, LoadedPlugin] = {}

    def register(self, plugin: LoadedPlugin) -> None:
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)

    def get(self, name: str) -> LoadedPlugin | None:
        return self._plugins.get(name)

    def get_all(self) -> dict[str, LoadedPlugin]:
        return dict(self._plugins)

    def get_enabled(self) -> dict[str, LoadedPlugin]:
        return {
            name: plugin
            for name, plugin in self._plugins.items()
            if plugin.is_enabled
        }

    def get_by_state(self, state: PluginState) -> list[LoadedPlugin]:
        return [p for p in self._plugins.values() if p.state == state]

    def list_plugins(self) -> list[dict[str, Any]]:
        return [plugin.to_dict() for plugin in self._plugins.values()]

    def enable(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        if plugin.state == PluginState.ERROR:
            return False
        plugin.state = PluginState.ENABLED
        return True

    def disable(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        plugin.state = PluginState.DISABLED
        return True

    def set_state(self, name: str, state: PluginState) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        plugin.state = state
        return True

    def set_error(self, name: str, error: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        plugin.state = PluginState.ERROR
        plugin.error = error
        return True

    def has_plugin(self, name: str) -> bool:
        return name in self._plugins

    def search(self, query: str) -> list[LoadedPlugin]:
        query_lower = query.lower()
        results: list[LoadedPlugin] = []
        for plugin in self._plugins.values():
            searchable = (
                f"{plugin.manifest.name} "
                f"{plugin.manifest.description} "
                f"{plugin.manifest.author}"
            ).lower()
            if query_lower in searchable:
                results.append(plugin)
        return results

    def clear(self) -> None:
        self._plugins.clear()

    def get_all_commands(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for plugin in self._plugins.values():
            if plugin.is_enabled:
                for cmd in plugin.loaded_commands:
                    result[cmd] = plugin.name
        return result

    def get_all_agents(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for plugin in self._plugins.values():
            if plugin.is_enabled:
                for agent in plugin.loaded_agents:
                    result[agent] = plugin.name
        return result

    def get_all_skills(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for plugin in self._plugins.values():
            if plugin.is_enabled:
                for skill in plugin.loaded_skills:
                    result[skill] = plugin.name
        return result

    def get_all_hooks(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for plugin in self._plugins.values():
            if plugin.is_enabled:
                for hook in plugin.loaded_hooks:
                    result[hook] = plugin.name
        return result
