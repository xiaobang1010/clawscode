from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class TaskStopInput(BaseModel):
    task_id: str = Field(description="要停止的后台任务 ID")


class TaskStopTool(Tool):
    name = "TaskStop"
    description = "停止指定的后台 Agent 任务。"
    input_schema = TaskStopInput
    is_readonly = False

    async def call(self, input: TaskStopInput, context: Any) -> ToolResult:
        from src.tools.agent import get_background_task

        task = get_background_task(input.task_id)
        if not task:
            return ToolResult(
                output=f"未找到后台任务: {input.task_id}",
                is_error=True,
            )

        if task.status != "running":
            return ToolResult(
                output=f"任务 {input.task_id} 已经处于 {task.status} 状态，无需停止"
            )

        task.cancel()
        return ToolResult(
            output=f"任务 {input.task_id} ({task.agent_name}) 已停止"
        )
