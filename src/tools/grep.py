from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class GrepInput(BaseModel):
    pattern: str = Field(description="搜索的正则表达式")
    path: str | None = Field(default=None, description="搜索目录")
    file_glob: str | None = Field(default=None, description="文件过滤，如 *.py")


class GrepTool(Tool):
    name = "Grep"
    description = "在文件内容中搜索"
    input_schema = GrepInput

    async def call(self, input: GrepInput, context: Any) -> ToolResult:
        base = Path(input.path or context.cwd)
        results: list[str] = []
        files = base.glob(input.file_glob or "**/*")
        for f in files:
            if f.is_file():
                try:
                    for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if re.search(input.pattern, line):
                            results.append(f"{f}:{i}: {line.strip()}")
                except Exception:
                    pass
            if len(results) >= 50:
                break
        output = "\n".join(results[:50])
        return ToolResult(output=output or "未找到匹配内容")
