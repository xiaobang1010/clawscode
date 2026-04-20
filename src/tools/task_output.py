from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class TaskOutputInput(BaseModel):
    task_id: str = Field(description="后台任务的 ID")
    wait: bool = Field(default=False, description="是否等待任务完成")


class TaskOutputTool(Tool):
    name = "TaskOutput"
    description = "查看后台 Agent 任务的输出。"
    input_schema = TaskOutputInput
    is_readonly = True

    async def call(self, input: TaskOutputInput, context: Any) -> ToolResult:
        from src.tools.agent import get_background_task

        task = get_background_task(input.task_id)
        if not task:
            return ToolResult(
                output=f"未找到后台任务: {input.task_id}",
                is_error=True,
            )

        if input.wait and task.status == "running":
            import asyncio
            for _ in range(60):
                await asyncio.sleep(1)
                if task.status != "running":
                    break

        status_text = {
            "running": "运行中",
            "done": "已完成",
            "error": "出错",
            "cancelled": "已取消",
        }.get(task.status, task.status)

        output = f"任务 {input.task_id} ({task.agent_name}) - 状态: {status_text}\n"
        if task.output:
            output += f"\n--- 输出 ---\n{task.output}"
        else:
            output += "\n暂无输出"

        return ToolResult(output=output)
