from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult
from src.services.cron_scheduler import get_cron_scheduler


class CronCreateInput(BaseModel):
    name: str = Field(description="定时任务名称")
    command: str = Field(description="要执行的命令")
    interval_seconds: float = Field(description="执行间隔（秒）", ge=1.0, le=86400.0)


class CronCreateTool(Tool):
    name = "CronCreate"
    description = "创建定时任务。任务将按指定间隔重复执行。"
    input_schema = CronCreateInput

    async def call(self, input: CronCreateInput, context: Any) -> ToolResult:
        scheduler = get_cron_scheduler()
        task = scheduler.create_task(
            name=input.name,
            command=input.command,
            interval_seconds=input.interval_seconds,
        )

        if not scheduler.is_running:
            await scheduler.start()

        return ToolResult(
            output=f"已创建定时任务: {task.name} (id={task.id}, 间隔={task.interval_seconds}s)\n"
            f"调度器状态: {'运行中' if scheduler.is_running else '已停止'}"
        )
