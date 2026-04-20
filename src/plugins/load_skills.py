from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.plugins.types import LoadedPlugin
from src.skills.types import SkillDefinition

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


class PluginSkillLoader:
    def __init__(self) -> None:
        self._loaded: dict[str, SkillDefinition] = {}

    def load(self, plugin: LoadedPlugin) -> list[str]:
        skills_dir = plugin.path / "skills"
        if not skills_dir.is_dir():
            return []

        loaded: list[str] = []

        for yaml_file in sorted(skills_dir.glob("*.yml")):
            name = self._load_skill_yaml(yaml_file, plugin.name)
            if name:
                loaded.append(name)
        for yaml_file in sorted(skills_dir.glob("*.yaml")):
            name = self._load_skill_yaml(yaml_file, plugin.name)
            if name:
                loaded.append(name)
        for md_file in sorted(skills_dir.glob("*.md")):
            name = self._load_skill_markdown(md_file, plugin.name)
            if name:
                loaded.append(name)

        plugin.loaded_skills = loaded
        return loaded

    def unload(self, plugin: LoadedPlugin) -> None:
        for skill_name in plugin.loaded_skills:
            self._loaded.pop(f"{plugin.name}:{skill_name}", None)
        plugin.loaded_skills = []

    def get(self, plugin_name: str, skill_name: str) -> SkillDefinition | None:
        return self._loaded.get(f"{plugin_name}:{skill_name}")

    def get_all(self) -> dict[str, SkillDefinition]:
        return dict(self._loaded)

    def _load_skill_yaml(self, filepath: Path, plugin_name: str) -> str | None:
        if yaml is None:
            return None

        try:
            content = filepath.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return None

            definition = self._parse_skill(data, filepath.stem, plugin_name)
            if definition:
                self._loaded[f"{plugin_name}:{definition.name}"] = definition
                logger.debug(
                    "Loaded skill '%s' from plugin '%s'",
                    definition.name,
                    plugin_name,
                )
                return definition.name
            return None
        except (OSError, ValueError, KeyError) as e:
            logger.warning(
                "Failed to load skill '%s' from plugin '%s': %s",
                filepath,
                plugin_name,
                e,
            )
            return None

    def _load_skill_markdown(self, filepath: Path, plugin_name: str) -> str | None:
        if yaml is None:
            return None

        try:
            content = filepath.read_text(encoding="utf-8")
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
            if not match:
                return None

            frontmatter_str = match.group(1)
            body = match.group(2).strip()
            data = yaml.safe_load(frontmatter_str)
            if not isinstance(data, dict):
                return None

            data.setdefault("getPromptForCommand", body)
            definition = self._parse_skill(data, filepath.stem, plugin_name)
            if definition:
                self._loaded[f"{plugin_name}:{definition.name}"] = definition
                logger.debug(
                    "Loaded skill '%s' from plugin '%s'",
                    definition.name,
                    plugin_name,
                )
                return definition.name
            return None
        except (OSError, ValueError, KeyError) as e:
            logger.warning(
                "Failed to load skill '%s' from plugin '%s': %s",
                filepath,
                plugin_name,
                e,
            )
            return None

    def _parse_skill(
        self, data: dict[str, Any], fallback_name: str, plugin_name: str
    ) -> SkillDefinition | None:
        name = data.get("name", fallback_name)
        if not name:
            return None

        return SkillDefinition(
            name=name,
            description=data.get("description", ""),
            when_to_use=data.get("whenToUse", data.get("when_to_use", "")),
            allowed_tools=data.get("allowedTools", data.get("allowed_tools", [])),
            get_prompt_for_command=data.get(
                "getPromptForCommand", data.get("get_prompt_for_command", "")
            ),
            aliases=data.get("aliases", []),
            metadata={"plugin": plugin_name, **data.get("metadata", {})},
        )
