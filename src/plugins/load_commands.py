from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from src.plugins.types import LoadedPlugin

logger = logging.getLogger(__name__)


class PluginCommandLoader:
    def __init__(self) -> None:
        self._loaded_handlers: dict[str, Any] = {}

    def load(self, plugin: LoadedPlugin) -> list[str]:
        commands_dir = plugin.path / "commands"
        if not commands_dir.is_dir():
            return []

        loaded: list[str] = []
        for py_file in sorted(commands_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            command_name = py_file.stem
            try:
                handler = self._load_command_module(py_file, plugin.name)
                if handler is not None:
                    self._loaded_handlers[f"{plugin.name}:{command_name}"] = handler
                    loaded.append(command_name)
                    logger.debug(
                        "Loaded command '%s' from plugin '%s'",
                        command_name,
                        plugin.name,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to load command '%s' from plugin '%s': %s",
                    command_name,
                    plugin.name,
                    e,
                )

        plugin.loaded_commands = loaded
        return loaded

    def unload(self, plugin: LoadedPlugin) -> None:
        for cmd in plugin.loaded_commands:
            self._loaded_handlers.pop(f"{plugin.name}:{cmd}", None)
        plugin.loaded_commands = []

    def get_handler(self, plugin_name: str, command_name: str) -> Any:
        return self._loaded_handlers.get(f"{plugin_name}:{command_name}")

    def get_all_handlers(self) -> dict[str, Any]:
        return dict(self._loaded_handlers)

    def _load_command_module(self, filepath: Path, plugin_name: str) -> Any:
        module_name = f"plugins.{plugin_name}.commands.{filepath.stem}"
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        handler = getattr(module, "handle", None)
        if handler is None:
            handler = getattr(module, "execute", None)

        return handler
