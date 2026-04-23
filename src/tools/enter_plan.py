from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.permissions import PermissionMode
from src.tool import Tool, ToolResult


class EnterPlanModeInput(BaseModel):
    plan_description: str = Field(
        default="",
        description="可选的规划描述，说明要规划什么内容",
    )


class EnterPlanModeTool(Tool):
    name = "EnterPlanMode"
    description = (
        "进入 Plan（规划）模式。在 Plan 模式下，系统仅允许只读操作（如读取文件、搜索代码），"
        "禁止所有写入操作（如编辑文件、执行命令）。适用于需要先分析和规划再执行的场景。"
    )
    input_schema = EnterPlanModeInput
    user_facing_name = "进入规划模式"
    is_readonly = True

    async def call(self, input: EnterPlanModeInput, context: Any) -> ToolResult:
        checker = getattr(context, "permission_checker", None)
        if checker is None:
            return ToolResult(
                output="无法切换模式：权限检查器不可用",
                is_error=True,
            )

        current_mode = checker.mode
        if current_mode == PermissionMode.PLAN:
            return ToolResult(output="已经在 Plan 模式中，无需重复切换。")

        checker.set_mode(PermissionMode.PLAN)
        context.settings.permission_mode = "plan"

        tools = getattr(context, "tools", None)
        if tools is not None:
            from src.services.agent_context import refresh_agent_definitions
            refreshed = refresh_agent_definitions(tools, permission_mode="plan")
            context.tools = refreshed

        lines = ["已进入 Plan（规划）模式。"]
        if input.plan_description:
            lines.append(f"规划目标: {input.plan_description}")
        lines.append("")
        lines.append("当前限制：")
        lines.append("  - 只允许只读操作（文件读取、代码搜索等）")
        lines.append("  - 禁止文件编辑、文件写入、命令执行")
        lines.append("  - 使用 ExitPlanMode 工具退出 Plan 模式")

        return ToolResult(output="\n".join(lines))
