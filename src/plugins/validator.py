from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.plugins.types import LoadedPlugin, PluginManifest

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ["name"]
_OPTIONAL_DIRS = ["commands", "agents", "skills", "hooks"]
_MAX_MANIFEST_SIZE = 64 * 1024


class PluginValidationError(Exception):
    def __init__(self, plugin_name: str, errors: list[str]):
        self.plugin_name = plugin_name
        self.errors = errors
        super().__init__(f"Plugin '{plugin_name}' validation failed: {'; '.join(errors)}")


class PluginValidator:
    def __init__(self, strict: bool = False):
        self._strict = strict

    def validate(self, plugin: LoadedPlugin) -> list[str]:
        errors: list[str] = []

        self._validate_manifest(plugin.manifest, errors)
        self._validate_structure(plugin, errors)

        return errors

    def validate_manifest(self, manifest: PluginManifest) -> list[str]:
        errors: list[str] = []
        self._validate_manifest(manifest, errors)
        return errors

    def is_valid(self, plugin: LoadedPlugin) -> bool:
        return len(self.validate(plugin)) == 0

    def _validate_manifest(self, manifest: PluginManifest, errors: list[str]) -> None:
        for field_name in _REQUIRED_FIELDS:
            value = getattr(manifest, field_name, None)
            if not value:
                errors.append(f"Missing required field: {field_name}")

        if manifest.name:
            invalid_chars = set('<>:"/\\|?*\0')
            if any(c in manifest.name for c in invalid_chars):
                errors.append(f"Plugin name contains invalid characters: {manifest.name}")

            if manifest.name.startswith(".") or manifest.name.startswith("-"):
                errors.append(f"Plugin name cannot start with '.' or '-': {manifest.name}")

        if manifest.version:
            parts = manifest.version.split(".")
            if len(parts) > 4:
                errors.append(f"Version has too many parts: {manifest.version}")

        for req in manifest.requires:
            if not isinstance(req, str) or not req.strip():
                errors.append(f"Invalid requirement: {req}")

    def _validate_structure(self, plugin: LoadedPlugin, errors: list[str]) -> None:
        if not plugin.path.is_dir():
            errors.append(f"Plugin path is not a directory: {plugin.path}")
            return

        has_manifest = (
            (plugin.path / "plugin.json").is_file()
            or (plugin.path / "plugin.yaml").is_file()
            or (plugin.path / "plugin.yml").is_file()
        )
        if not has_manifest:
            errors.append("No plugin manifest file found (plugin.json or plugin.yaml)")

        provided_components = []
        for dir_name in _OPTIONAL_DIRS:
            dir_path = plugin.path / dir_name
            if dir_path.is_dir():
                files = list(dir_path.iterdir())
                if files:
                    provided_components.append(dir_name)

        manifest = plugin.manifest
        declared = (
            manifest.provides_commands
            + manifest.provides_agents
            + manifest.provides_skills
            + manifest.provides_hooks
        )
        if self._strict and declared and not provided_components:
            errors.append("Manifest declares provides but no component directories exist")

    def validate_path(self, path: Path) -> list[str]:
        errors: list[str] = []

        if not path.is_dir():
            errors.append(f"Path is not a directory: {path}")
            return errors

        try:
            items = list(path.iterdir())
        except PermissionError:
            errors.append(f"Permission denied: {path}")
            return errors

        if not items:
            errors.append(f"Plugin directory is empty: {path}")

        return errors
