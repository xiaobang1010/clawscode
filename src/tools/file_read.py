from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class FileReadInput(BaseModel):
    file_path: str = Field(description="文件路径")
    offset: int | None = Field(default=None, description="起始行号")
    limit: int | None = Field(default=None, description="读取行数")


class FileReadTool(Tool):
    name = "FileRead"
    description = "读取文件内容"
    input_schema = FileReadInput

    async def call(self, input: FileReadInput, context: Any) -> ToolResult:
        path = Path(input.file_path)
        if not path.exists():
            return ToolResult(output=f"文件不存在: {input.file_path}", is_error=True)
        if not path.is_file():
            return ToolResult(output=f"不是文件: {input.file_path}", is_error=True)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = (input.offset or 1) - 1
        end = start + (input.limit or len(lines))
        selected = lines[start:end]
        numbered = [f"{i + 1:6}\u2192{line}" for i, line in enumerate(selected, start=start + 1)]
        return ToolResult(output="\n".join(numbered))
