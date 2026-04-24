from __future__ import annotations

from typing import Any

from src.skills.types import SkillDefinition


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, SkillDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, skill: SkillDefinition) -> None:
        if skill.is_enabled is not None and not skill.is_enabled():
            return
        self._skills[skill.name] = skill
        for alias in skill.aliases:
            self._aliases[alias] = skill.name

    def unregister(self, name: str) -> None:
        skill = self._skills.pop(name, None)
        if skill:
            for alias in skill.aliases:
                self._aliases.pop(alias, None)

    def get(self, name_or_alias: str) -> SkillDefinition | None:
        name = self._aliases.get(name_or_alias, name_or_alias)
        skill = self._skills.get(name)
        if skill and skill.is_enabled is not None and not skill.is_enabled():
            return None
        return skill

    def get_all(self) -> dict[str, SkillDefinition]:
        return {
            name: skill for name, skill in self._skills.items()
            if skill.is_enabled is None or skill.is_enabled()
        }

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "when_to_use": skill.when_to_use,
                "aliases": skill.aliases,
            }
            for skill in self._skills.values()
            if skill.is_enabled is None or skill.is_enabled()
        ]

    def search(self, query: str) -> list[SkillDefinition]:
        query_lower = query.lower()
        results: list[SkillDefinition] = []
        for skill in self._skills.values():
            if skill.is_enabled is not None and not skill.is_enabled():
                continue
            searchable = f"{skill.name} {skill.description} {skill.when_to_use}".lower()
            if skill.search_hint if hasattr(skill, 'search_hint') else "":
                searchable += f" {skill.search_hint}"
            if query_lower in searchable:
                results.append(skill)
        return results

    def has_skill(self, name_or_alias: str) -> bool:
        return self.get(name_or_alias) is not None
