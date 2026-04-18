from __future__ import annotations

from typing import Any

from src.skills.types import SkillDefinition


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, SkillDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, skill: SkillDefinition) -> None:
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
        return self._skills.get(name)

    def get_all(self) -> dict[str, SkillDefinition]:
        return dict(self._skills)

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "when_to_use": skill.when_to_use,
                "aliases": skill.aliases,
            }
            for skill in self._skills.values()
        ]

    def search(self, query: str) -> list[SkillDefinition]:
        query_lower = query.lower()
        results: list[SkillDefinition] = []
        for skill in self._skills.values():
            searchable = f"{skill.name} {skill.description} {skill.when_to_use}".lower()
            if query_lower in searchable:
                results.append(skill)
        return results

    def has_skill(self, name_or_alias: str) -> bool:
        name = self._aliases.get(name_or_alias, name_or_alias)
        return name in self._skills
