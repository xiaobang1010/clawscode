from __future__ import annotations

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
        if input.arguments:
            try:
                prompt = prompt.format(**input.arguments)
            except (KeyError, IndexError):
                pass

        return ToolResult(
            output=f'Skill "{skill.name}" 已加载。\n\n{prompt}'
        )

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
