from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.plugins.types import LoadedPlugin, PluginManifest, PluginState

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


class PluginLoader:
    def __init__(self, search_paths: list[Path] | None = None):
        self._search_paths = search_paths or []
        self._loaded: dict[str, LoadedPlugin] = {}

    def add_search_path(self, path: Path) -> None:
        if path not in self._search_paths:
            self._search_paths.append(path)

    def load_all(self) -> dict[str, LoadedPlugin]:
        for path in self._search_paths:
            if path.is_dir():
                self._discover_from_directory(path)
        return dict(self._loaded)

    def get(self, name: str) -> LoadedPlugin | None:
        return self._loaded.get(name)

    def get_all(self) -> dict[str, LoadedPlugin]:
        return dict(self._loaded)

    def register(self, plugin: LoadedPlugin) -> None:
        self._loaded[plugin.name] = plugin

    def remove(self, name: str) -> None:
        self._loaded.pop(name, None)

    def _discover_from_directory(self, directory: Path) -> None:
        if not directory.is_dir():
            return

        for entry in sorted(directory.iterdir()):
            if not entry.is_dir():
                continue

            manifest = self._load_manifest(entry)
            if manifest is None:
                continue

            plugin_name = manifest.name or entry.name
            if plugin_name in self._loaded:
                continue

            plugin = LoadedPlugin(
                manifest=manifest,
                path=entry,
                state=PluginState.DISCOVERED,
            )
            self._loaded[plugin_name] = plugin

    def _load_manifest(self, plugin_dir: Path) -> PluginManifest | None:
        json_path = plugin_dir / "plugin.json"
        if json_path.is_file():
            return self._load_json_manifest(json_path)

        yaml_path = plugin_dir / "plugin.yaml"
        if yaml_path.is_file():
            return self._load_yaml_manifest(yaml_path)

        yml_path = plugin_dir / "plugin.yml"
        if yml_path.is_file():
            return self._load_yaml_manifest(yml_path)

        return None

    def _load_json_manifest(self, filepath: Path) -> PluginManifest | None:
        try:
            content = filepath.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                return None
            return PluginManifest.from_dict(data)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to load plugin manifest %s: %s", filepath, e)
            return None

    def _load_yaml_manifest(self, filepath: Path) -> PluginManifest | None:
        if yaml is None:
            return None

        try:
            content = filepath.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return None
            return PluginManifest.from_dict(data)
        except (OSError, ValueError, KeyError) as e:
            logger.warning("Failed to load plugin manifest %s: %s", filepath, e)
            return None
