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
    description = "通过精确字符串匹配编辑文件。要求 old_string 在文件中恰好出现一次。"
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
            locations = []
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                if input.old_string in line:
                    locations.append(f"  行 {i}: {line.strip()[:80]}")
            return ToolResult(
                output=f"找到 {count} 处匹配，需要更精确的匹配:\n" + "\n".join(locations[:10]),
                is_error=True,
            )

        _backup_file(path, context)

        new_content = content.replace(input.old_string, input.new_string)
        path.write_text(new_content, encoding="utf-8")

        old_lines = input.old_string.count("\n") + 1
        new_lines = input.new_string.count("\n") + 1
        return ToolResult(output=f"已编辑 {input.file_path} ({old_lines} 行 -> {new_lines} 行)")


def _backup_file(path: Path, context: Any) -> None:
    file_history = getattr(context, "file_history", None)
    if file_history is None:
        return

    resolved = str(path.resolve())
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        file_history.append({"path": resolved, "content": content})
        if len(file_history) > 50:
            file_history.pop(0)
    except Exception:
        pass
