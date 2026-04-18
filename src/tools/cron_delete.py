from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult
from src.services.cron_scheduler import get_cron_scheduler


class CronDeleteInput(BaseModel):
    task_id: str = Field(description="定时任务 ID")


class CronDeleteTool(Tool):
    name = "CronDelete"
    description = "删除定时任务。"
    input_schema = CronDeleteInput

    async def call(self, input: CronDeleteInput, context: Any) -> ToolResult:
        scheduler = get_cron_scheduler()
        task = scheduler.delete_task(input.task_id)
        if task is None:
            return ToolResult(output=f"未找到定时任务: {input.task_id}", is_error=True)
        return ToolResult(output=f"已删除定时任务: {task.name} (id={task.id})")
