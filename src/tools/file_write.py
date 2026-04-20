from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class FileWriteInput(BaseModel):
    file_path: str = Field(description="要写入的文件路径")
    content: str = Field(description="要写入的内容")


class FileWriteTool(Tool):
    name = "FileWrite"
    description = "创建新文件或覆盖已有文件的内容。对于已有文件，必须先用 FileRead 读取过才能写入。"
    input_schema = FileWriteInput

    async def call(self, input: FileWriteInput, context: Any) -> ToolResult:
        path = Path(input.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(input.content, encoding="utf-8")
        lines = input.content.count("\n") + (0 if input.content.endswith("\n") else 1)
        return ToolResult(output=f"已写入 {input.file_path} ({lines} 行)")

    async def check_permissions(self, input: FileWriteInput, context: Any):
        from src.tool import PermissionResult

        path = Path(input.file_path)
        if path.exists():
            read_files = getattr(context, "read_files", set())
            if str(path.resolve()) not in read_files:
                return PermissionResult.ASK
        return PermissionResult.ALLOW
