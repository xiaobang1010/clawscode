from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class SkillToolInput(BaseModel):
    command: str = Field(description="要执行的 Skill 名称或别名")
    arguments: dict[str, Any] = Field(default_factory=dict, description="传递给 Skill 的参数")


class SkillTool(Tool):
    name = "Skill"
    description = "加载和执行技能模块。技能是预定义的任务模板，提供特定领域的专业提示词和工作流程。"
    input_schema = SkillToolInput
    user_facing_name = "Skill"
    is_readonly = True

    async def call(self, input: SkillToolInput, context: Any) -> ToolResult:
        registry = self._get_registry()
        if registry is None:
            return ToolResult(output="", error="Skill 系统未初始化", is_error=True)

        skill = registry.get(input.command)
        if skill is None:
            available = ", ".join(sorted(registry.get_all().keys()))
            return ToolResult(
                output="",
                error=f"未找到 Skill: {input.command}\n可用 Skill: {available}",
                is_error=True,
            )

        prompt = skill.get_prompt_for_command

        prompt = self._apply_variable_substitutions(prompt, skill, context)

        if skill.disable_model_invocation:
            return ToolResult(
                output=prompt,
                metadata={"allowed_tools": skill.allowed_tools, "skill_name": skill.name},
            )

        if input.arguments:
            try:
                prompt = prompt.format(**input.arguments)
            except (KeyError, IndexError):
                pass

        if skill.context == "fork":
            return ToolResult(
                output=f'Skill "{skill.name}" (fork 模式) 已启动。\n\n{prompt}',
                metadata={
                    "allowed_tools": skill.allowed_tools,
                    "skill_name": skill.name,
                    "context": "fork",
                    "agent": skill.agent,
                },
            )

        base_dir_prefix = ""
        if skill.skill_dir:
            base_dir_prefix = f"Base directory for this skill: {skill.skill_dir}\n\n"

        return ToolResult(
            output=f'{base_dir_prefix}Skill "{skill.name}" 已加载。\n\n{prompt}',
            metadata={"allowed_tools": skill.allowed_tools, "skill_name": skill.name},
        )

    def _apply_variable_substitutions(self, prompt: str, skill: Any, context: Any) -> str:
        if skill.skill_dir:
            prompt = prompt.replace("${CLAWSCODE_SKILL_DIR}", skill.skill_dir)

        session_id = getattr(context, "session_id", "")
        if session_id:
            prompt = prompt.replace("${CLAWSCODE_SESSION_ID}", session_id)

        return prompt

    def _get_registry(self):
        from src.skills.registry import SkillRegistry

        if not hasattr(SkillTool, "_registry_instance"):
            SkillTool._registry_instance = SkillRegistry()
            from src.skills.bundled import register_builtins
            register_builtins(SkillTool._registry_instance)
        return SkillTool._registry_instance

    @classmethod
    def set_registry(cls, registry) -> None:
        cls._registry_instance = registry
