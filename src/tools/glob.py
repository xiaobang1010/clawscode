from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class GlobInput(BaseModel):
    pattern: str = Field(description="glob 模式，如 **/*.py")
    path: str | None = Field(default=None, description="搜索目录")


class GlobTool(Tool):
    name = "Glob"
    description = "按模式搜索文件"
    input_schema = GlobInput

    async def call(self, input: GlobInput, context: Any) -> ToolResult:
        base = Path(input.path or context.cwd)
        matches = sorted(base.glob(input.pattern))
        output = "\n".join(str(m) for m in matches[:100])
        return ToolResult(output=output or "未找到匹配文件")
