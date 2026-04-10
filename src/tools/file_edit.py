from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class FileEditInput(BaseModel):
    file_path: str = Field(description="文件路径")
    old_string: str = Field(description="要替换的原始字符串")
    new_string: str = Field(description="替换后的新字符串")


class FileEditTool(Tool):
    name = "FileEdit"
    description = "通过精确字符串匹配编辑文件"
    input_schema = FileEditInput

    async def call(self, input: FileEditInput, context: Any) -> ToolResult:
        path = Path(input.file_path)
        if not path.exists():
            return ToolResult(output=f"文件不存在: {input.file_path}", is_error=True)
        content = path.read_text(encoding="utf-8")
        if input.old_string not in content:
            return ToolResult(output=f"未找到匹配的字符串", is_error=True)
        count = content.count(input.old_string)
        if count > 1:
            return ToolResult(output=f"找到 {count} 处匹配，需要更精确的匹配", is_error=True)
        new_content = content.replace(input.old_string, input.new_string)
        path.write_text(new_content, encoding="utf-8")
        return ToolResult(output=f"已编辑 {input.file_path}")
