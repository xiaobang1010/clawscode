from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.plugins.loader import PluginLoader
from src.plugins.load_agents import PluginAgentLoader
from src.plugins.load_commands import PluginCommandLoader
from src.plugins.load_hooks import PluginHookLoader
from src.plugins.load_skills import PluginSkillLoader
from src.plugins.registry import PluginRegistry
from src.plugins.types import LoadedPlugin, PluginState
from src.plugins.validator import PluginValidator

logger = logging.getLogger(__name__)


class PluginIsolationError(Exception):
    def __init__(self, plugin_name: str, message: str):
        self.plugin_name = plugin_name
        super().__init__(f"Plugin '{plugin_name}' isolation error: {message}")


class PluginManager:
    def __init__(self, search_paths: list[Path] | None = None) -> None:
        self._loader = PluginLoader(search_paths)
        self._validator = PluginValidator()
        self._registry = PluginRegistry()
        self._command_loader = PluginCommandLoader()
        self._agent_loader = PluginAgentLoader()
        self._skill_loader = PluginSkillLoader()
        self._hook_loader = PluginHookLoader()
        self._disabled_plugins: set[str] = set()
        self._isolation_errors: dict[str, list[str]] = {}

    def discover(self) -> dict[str, LoadedPlugin]:
        discovered = self._loader.load_all()
        for name, plugin in discovered.items():
            if name in self._disabled_plugins:
                plugin.state = PluginState.DISABLED
                continue

            errors = self._validator.validate(plugin)
            if errors:
                plugin.state = PluginState.ERROR
                plugin.error = "; ".join(errors)
                self._isolation_errors[name] = errors
                logger.warning(
                    "Plugin '%s' validation failed: %s", name, errors
                )
            else:
                plugin.state = PluginState.DISCOVERED

            self._registry.register(plugin)
        return discovered

    def load_plugin(self, name: str) -> bool:
        plugin = self._loader.get(name)
        if plugin is None:
            logger.warning("Plugin '%s' not found", name)
            return False

        if plugin.state == PluginState.ERROR:
            errors = self._validator.validate(plugin)
            if errors:
                plugin.error = "; ".join(errors)
                return False
            plugin.error = None

        try:
            self._load_components(plugin)
            plugin.state = PluginState.LOADED
            self._registry.register(plugin)
            self._isolation_errors.pop(name, None)
            return True
        except Exception as e:
            self._handle_isolation_error(plugin, str(e))
            return False

    def load_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name in list(self._loader.get_all().keys()):
            plugin = self._loader.get(name)
            if plugin and plugin.state not in (PluginState.DISABLED, PluginState.ERROR):
                results[name] = self.load_plugin(name)
        return results

    def enable_plugin(self, name: str) -> bool:
        plugin = self._registry.get(name)
        if plugin is None:
            plugin = self._loader.get(name)
            if plugin is None:
                return False

        if plugin.state == PluginState.DISABLED:
            plugin.state = PluginState.DISCOVERED

        if not plugin.is_loaded:
            success = self.load_plugin(name)
            if not success:
                return False

        return self._registry.enable(name)

    def disable_plugin(self, name: str) -> bool:
        plugin = self._registry.get(name)
        if plugin is None:
            return False

        self._unload_components(plugin)
        self._disabled_plugins.add(name)
        return self._registry.disable(name)

    def refresh_plugin(self, name: str) -> bool:
        plugin = self._loader.get(name)
        if plugin is None:
            return False

        was_enabled = plugin.is_enabled

        self._unload_components(plugin)
        self._registry.unregister(name)

        self._loader.remove(name)

        manifest = self._loader._load_manifest(plugin.path)
        if manifest is None:
            return False

        plugin_name = manifest.name or plugin.path.name
        new_plugin = LoadedPlugin(
            manifest=manifest,
            path=plugin.path,
            state=PluginState.DISCOVERED,
        )
        self._loader.register(new_plugin)

        errors = self._validator.validate(new_plugin)
        if errors:
            new_plugin.state = PluginState.ERROR
            new_plugin.error = "; ".join(errors)
            self._registry.register(new_plugin)
            return False

        if was_enabled:
            self.load_plugin(plugin_name)
            self._registry.enable(plugin_name)
        else:
            self._registry.register(new_plugin)

        self._isolation_errors.pop(name, None)
        return True

    def refresh_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name in list(self._loader.get_all().keys()):
            results[name] = self.refresh_plugin(name)
        return results

    def get_plugin(self, name: str) -> LoadedPlugin | None:
        return self._registry.get(name)

    def get_all_plugins(self) -> dict[str, LoadedPlugin]:
        return self._registry.get_all()

    def get_enabled_plugins(self) -> dict[str, LoadedPlugin]:
        return self._registry.get_enabled()

    def list_plugins(self) -> list[dict[str, Any]]:
        return self._registry.list_plugins()

    def search_plugins(self, query: str) -> list[LoadedPlugin]:
        return self._registry.search(query)

    def get_all_commands(self) -> dict[str, str]:
        return self._registry.get_all_commands()

    def get_all_agents(self) -> dict[str, str]:
        return self._registry.get_all_agents()

    def get_all_skills(self) -> dict[str, str]:
        return self._registry.get_all_skills()

    def get_all_hooks(self) -> dict[str, str]:
        return self._registry.get_all_hooks()

    def get_command_handler(self, plugin_name: str, command_name: str) -> Any:
        return self._command_loader.get_handler(plugin_name, command_name)

    def get_agent_definition(self, plugin_name: str, agent_name: str) -> Any:
        return self._agent_loader.get(plugin_name, agent_name)

    def get_skill_definition(self, plugin_name: str, skill_name: str) -> Any:
        return self._skill_loader.get(plugin_name, skill_name)

    def get_hook_definition(self, plugin_name: str, hook_name: str) -> Any:
        return self._hook_loader.get(plugin_name, hook_name)

    def get_isolation_errors(self, name: str) -> list[str]:
        return self._isolation_errors.get(name, [])

    def add_search_path(self, path: Path) -> None:
        self._loader.add_search_path(path)

    def set_disabled_plugins(self, names: set[str]) -> None:
        self._disabled_plugins = set(names)

    def _load_components(self, plugin: LoadedPlugin) -> None:
        commands = self._command_loader.load(plugin)
        agents = self._agent_loader.load(plugin)
        skills = self._skill_loader.load(plugin)
        hooks = self._hook_loader.load(plugin)

        logger.info(
            "Loaded plugin '%s': %d commands, %d agents, %d skills, %d hooks",
            plugin.name,
            len(commands),
            len(agents),
            len(skills),
            len(hooks),
        )

    def _unload_components(self, plugin: LoadedPlugin) -> None:
        self._command_loader.unload(plugin)
        self._agent_loader.unload(plugin)
        self._skill_loader.unload(plugin)
        self._hook_loader.unload(plugin)

    def _handle_isolation_error(self, plugin: LoadedPlugin, error: str) -> None:
        plugin.state = PluginState.ERROR
        plugin.error = error
        self._isolation_errors[plugin.name] = [error]
        self._registry.register(plugin)
        logger.error(
            "Plugin '%s' isolated due to error: %s", plugin.name, error
        )
