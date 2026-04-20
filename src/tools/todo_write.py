from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class TodoItemInput(BaseModel):
    id: str = Field(description="任务唯一标识")
    content: str = Field(description="任务内容描述")
    status: str = Field(default="pending", description="任务状态: pending/in_progress/completed")
    priority: str = Field(default="medium", description="优先级: high/medium/low")


class TodoWriteInput(BaseModel):
    todos: list[TodoItemInput] = Field(description="完整的任务列表，会替换现有列表")


class TodoWriteTool(Tool):
    name = "TodoWrite"
    description = "创建和管理任务列表。传入完整的任务列表来替换现有列表。每个任务包含 id、content、status、priority。"
    input_schema = TodoWriteInput

    async def call(self, input: TodoWriteInput, context: Any) -> ToolResult:
        valid_statuses = {"pending", "in_progress", "completed"}
        valid_priorities = {"high", "medium", "low"}

        for todo in input.todos:
            if todo.status not in valid_statuses:
                return ToolResult(output=f"无效状态: {todo.status}，有效值: {valid_statuses}", is_error=True)
            if todo.priority not in valid_priorities:
                return ToolResult(output=f"无效优先级: {todo.priority}，有效值: {valid_priorities}", is_error=True)

        from src.state import TodoItem

        context.todo_list = [
            TodoItem(id=t.id, content=t.content, status=t.status, priority=t.priority)
            for t in input.todos
        ]

        summary_lines = []
        status_icons = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}
        for t in context.todo_list:
            icon = status_icons.get(t.status, "⏳")
            summary_lines.append(f"  {icon} [{t.priority}] {t.content}")

        return ToolResult(output=f"已更新 {len(context.todo_list)} 个任务:\n" + "\n".join(summary_lines))
