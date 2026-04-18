from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.tool import Tool, ToolResult
from src.services.cron_scheduler import get_cron_scheduler


class CronListInput(BaseModel):
    pass


class CronListTool(Tool):
    name = "CronList"
    description = "列出所有定时任务。"
    input_schema = CronListInput
    is_readonly = True

    async def call(self, input: CronListInput, context: Any) -> ToolResult:
        scheduler = get_cron_scheduler()
        tasks = scheduler.list_tasks()

        if not tasks:
            return ToolResult(
                output=f"无定时任务（调度器: {'运行中' if scheduler.is_running else '已停止'}）"
            )

        lines = [f"定时任务 ({len(tasks)} 个, 调度器: {'运行中' if scheduler.is_running else '已停止'}):\n"]
        for task in tasks:
            status = "启用" if task.enabled else "禁用"
            last_run = task.last_run.strftime("%H:%M:%S") if task.last_run else "未执行"
            lines.append(
                f"  [{task.id}] {task.name} - {status}\n"
                f"    命令: {task.command}\n"
                f"    间隔: {task.interval_seconds}s | 执行次数: {task.run_count} | 上次: {last_run}"
            )
            if task.last_error:
                lines.append(f"    最后错误: {task.last_error}")

        return ToolResult(output="\n".join(lines))
