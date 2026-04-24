from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.skills.types import SkillDefinition

try:
    import yaml
except ImportError:
    yaml = None


class SkillLoader:
    def __init__(self, search_paths: list[Path] | None = None):
        self._search_paths = search_paths or []
        self._loaded: dict[str, SkillDefinition] = {}

    def add_search_path(self, path: Path) -> None:
        if path not in self._search_paths:
            self._search_paths.append(path)

    def load_all(self) -> dict[str, SkillDefinition]:
        for path in self._search_paths:
            if path.is_dir():
                self._load_from_directory(path)
        return dict(self._loaded)

    def get(self, name: str) -> SkillDefinition | None:
        return self._loaded.get(name)

    def get_all(self) -> dict[str, SkillDefinition]:
        return dict(self._loaded)

    def register(self, definition: SkillDefinition) -> None:
        self._loaded[definition.name] = definition

    def _load_from_directory(self, directory: Path) -> None:
        if not directory.is_dir():
            return

        for yaml_file in sorted(directory.glob("*.yml")):
            self._load_yaml_file(yaml_file)
        for yaml_file in sorted(directory.glob("*.yaml")):
            self._load_yaml_file(yaml_file)
        for md_file in sorted(directory.glob("*.md")):
            self._load_markdown_file(md_file)

    def _load_yaml_file(self, filepath: Path) -> None:
        if yaml is None:
            return

        try:
            content = filepath.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return
            definition = self._parse_definition(data, filepath.stem, str(filepath.parent))
            if definition:
                self._loaded[definition.name] = definition
        except (OSError, ValueError, KeyError):
            pass

    def _load_markdown_file(self, filepath: Path) -> None:
        if yaml is None:
            return

        try:
            content = filepath.read_text(encoding="utf-8")
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
            if not match:
                return
            frontmatter_str = match.group(1)
            body = match.group(2).strip()
            data = yaml.safe_load(frontmatter_str)
            if not isinstance(data, dict):
                return
            data["getPromptForCommand"] = data.get("getPromptForCommand", body)
            definition = self._parse_definition(data, filepath.stem, str(filepath.parent))
            if definition:
                self._loaded[definition.name] = definition
        except (OSError, ValueError, KeyError):
            pass

    def _parse_definition(self, data: dict[str, Any], fallback_name: str, skill_dir: str = "") -> SkillDefinition | None:
        name = data.get("name", fallback_name)
        if not name:
            return None

        return SkillDefinition(
            name=name,
            description=data.get("description", ""),
            when_to_use=data.get("whenToUse", data.get("when_to_use", "")),
            allowed_tools=data.get("allowedTools", data.get("allowed_tools", [])),
            get_prompt_for_command=data.get("getPromptForCommand", data.get("get_prompt_for_command", "")),
            aliases=data.get("aliases", []),
            metadata=data.get("metadata", {}),
            hooks=data.get("hooks", None),
            context=data.get("context", "inline"),
            skill_dir=skill_dir or None,
            agent=data.get("agent", None),
            files=data.get("files", None),
            disable_model_invocation=data.get("disableModelInvocation", data.get("disable_model_invocation", False)),
        )
