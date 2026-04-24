from __future__ import annotations

from src.skills.types import SkillDefinition
from src.skills.bundled.batch import create_batch_skill
from src.skills.bundled.debug import create_debug_skill
from src.skills.bundled.loop import create_loop_skill
from src.skills.bundled.stuck import create_stuck_skill
from src.skills.bundled.verify import create_verify_skill
from src.skills.bundled.remember import create_remember_skill
from src.skills.bundled.simplify import create_simplify_skill
from src.skills.bundled.dream import create_dream_skill


def get_builtin_skills() -> list[SkillDefinition]:
    return [
        create_batch_skill(),
        create_debug_skill(),
        create_loop_skill(),
        create_stuck_skill(),
        create_verify_skill(),
        create_remember_skill(),
        create_simplify_skill(),
        create_dream_skill(),
    ]


def register_builtins(registry_or_dict) -> None:
    from src.skills.registry import SkillRegistry

    if isinstance(registry_or_dict, SkillRegistry):
        for skill in get_builtin_skills():
            registry_or_dict.register(skill)
    elif isinstance(registry_or_dict, dict):
        for skill in get_builtin_skills():
            registry_or_dict[skill.name] = skill
