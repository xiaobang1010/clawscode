from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.hooks.types import HookDefinition, HookEvent, HookType
from src.plugins.types import LoadedPlugin

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


class PluginHookLoader:
    def __init__(self) -> None:
        self._loaded: dict[str, HookDefinition] = {}

    def load(self, plugin: LoadedPlugin) -> list[str]:
        hooks_dir = plugin.path / "hooks"
        if not hooks_dir.is_dir():
            return []

        loaded: list[str] = []

        hooks_yaml = hooks_dir / "hooks.yaml"
        if hooks_yaml.is_file():
            names = self._load_hooks_file(hooks_yaml, plugin.name)
            loaded.extend(names)

        hooks_yml = hooks_dir / "hooks.yml"
        if hooks_yml.is_file():
            names = self._load_hooks_file(hooks_yml, plugin.name)
            loaded.extend(names)

        hooks_json = hooks_dir / "hooks.json"
        if hooks_json.is_file():
            names = self._load_hooks_json(hooks_json, plugin.name)
            loaded.extend(names)

        for yaml_file in sorted(hooks_dir.glob("*.yml")):
            if yaml_file.name in ("hooks.yml",):
                continue
            names = self._load_hooks_file(yaml_file, plugin.name)
            loaded.extend(names)
        for yaml_file in sorted(hooks_dir.glob("*.yaml")):
            if yaml_file.name in ("hooks.yaml",):
                continue
            names = self._load_hooks_file(yaml_file, plugin.name)
            loaded.extend(names)

        plugin.loaded_hooks = loaded
        return loaded

    def unload(self, plugin: LoadedPlugin) -> None:
        for hook_name in plugin.loaded_hooks:
            self._loaded.pop(f"{plugin.name}:{hook_name}", None)
        plugin.loaded_hooks = []

    def get(self, plugin_name: str, hook_name: str) -> HookDefinition | None:
        return self._loaded.get(f"{plugin_name}:{hook_name}")

    def get_all(self) -> dict[str, HookDefinition]:
        return dict(self._loaded)

    def _load_hooks_file(self, filepath: Path, plugin_name: str) -> list[str]:
        if yaml is None:
            return []

        try:
            content = filepath.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return []

            hooks_data = data.get("hooks", [])
            if not isinstance(hooks_data, list):
                hooks_data = [data] if isinstance(data, dict) else []

            return self._parse_hooks_list(hooks_data, plugin_name)
        except (OSError, ValueError, KeyError) as e:
            logger.warning(
                "Failed to load hooks '%s' from plugin '%s': %s",
                filepath,
                plugin_name,
                e,
            )
            return []

    def _load_hooks_json(self, filepath: Path, plugin_name: str) -> list[str]:
        import json

        try:
            content = filepath.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                return []

            hooks_data = data.get("hooks", [])
            if not isinstance(hooks_data, list):
                hooks_data = [data] if isinstance(data, dict) else []

            return self._parse_hooks_list(hooks_data, plugin_name)
        except (OSError, ValueError, KeyError) as e:
            logger.warning(
                "Failed to load hooks '%s' from plugin '%s': %s",
                filepath,
                plugin_name,
                e,
            )
            return []

    def _parse_hooks_list(
        self, hooks_data: list[dict], plugin_name: str
    ) -> list[str]:
        loaded: list[str] = []

        for cfg in hooks_data:
            if not isinstance(cfg, dict):
                continue

            try:
                name = cfg.get("name", "")
                if not name:
                    continue

                full_name = f"{plugin_name}:{name}"
                hook = HookDefinition(
                    name=full_name,
                    event=HookEvent(cfg["event"]),
                    hook_type=HookType(cfg["type"]),
                    command=cfg.get("command", ""),
                    url=cfg.get("url", ""),
                    agent_type=cfg.get("agent_type", ""),
                    timeout=float(cfg.get("timeout", 30.0)),
                    enabled=cfg.get("enabled", True),
                    metadata={"plugin": plugin_name, **cfg.get("metadata", {})},
                )
                self._loaded[full_name] = hook
                loaded.append(name)
                logger.debug(
                    "Loaded hook '%s' from plugin '%s'", name, plugin_name
                )
            except (KeyError, ValueError) as e:
                logger.warning(
                    "Skipping invalid hook in plugin '%s': %s", plugin_name, e
                )
                continue

        return loaded
