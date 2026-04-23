from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.permissions import PermissionMode
from src.tool import Tool, ToolResult


class ExitPlanModeInput(BaseModel):
    summary: str = Field(
        default="",
        description="可选的规划总结，描述规划结果和下一步行动",
    )


class ExitPlanModeTool(Tool):
    name = "ExitPlanMode"
    description = (
        "退出 Plan（规划）模式，恢复默认权限模式。退出后所有工具恢复可用。"
        "应在完成分析和规划后调用此工具。"
    )
    input_schema = ExitPlanModeInput
    user_facing_name = "退出规划模式"
    is_readonly = True

    async def call(self, input: ExitPlanModeInput, context: Any) -> ToolResult:
        checker = getattr(context, "permission_checker", None)
        if checker is None:
            return ToolResult(
                output="无法切换模式：权限检查器不可用",
                is_error=True,
            )

        current_mode = checker.mode
        if current_mode != PermissionMode.PLAN:
            return ToolResult(
                output=f"当前不在 Plan 模式中（当前模式: {current_mode.value}），无需退出。",
            )

        checker.set_mode(PermissionMode.DEFAULT)
        context.settings.permission_mode = "default"

        tools = getattr(context, "tools", None)
        if tools is not None:
            from src.services.agent_context import refresh_agent_definitions
            refreshed = refresh_agent_definitions(tools, permission_mode="default")
            context.tools = refreshed

        lines = ["已退出 Plan 模式，恢复默认权限。"]
        lines.append("所有工具已恢复可用。")
        if input.summary:
            lines.append("")
            lines.append(f"规划总结: {input.summary}")

        return ToolResult(output="\n".join(lines))
