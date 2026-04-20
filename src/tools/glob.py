from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class GlobInput(BaseModel):
    pattern: str = Field(description="glob 模式，如 **/*.py")
    path: str | None = Field(default=None, description="搜索目录")
    ignore: list[str] | None = Field(default=None, description="忽略模式列表")
    sort_by: str = Field(default="name", description="排序方式: name/modified")


class GlobTool(Tool):
    name = "Glob"
    description = "按模式搜索文件。支持忽略模式、排序方式选择和 ripgrep 加速。"
    input_schema = GlobInput
    is_readonly = True

    async def call(self, input: GlobInput, context: Any) -> ToolResult:
        base = Path(input.path or context.cwd)

        if shutil.which("rg"):
            return await self._ripgrep(input, base)

        return self._pure_python(input, base)

    async def _ripgrep(self, input: GlobInput, base: Path) -> ToolResult:
        cmd = ["rg", "--files", "--color", "never"]
        if input.ignore:
            for pattern in input.ignore:
                cmd.extend(["--glob", f"!{pattern}"])
        cmd.append(str(base))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)

        lines = stdout.decode(errors="replace").strip().splitlines()
        matches = [line for line in lines if _matches_glob(line, input.pattern)]

        if input.sort_by == "modified":
            matches.sort(key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0, reverse=True)
        else:
            matches.sort()

        output = "\n".join(matches[:100])
        return ToolResult(output=output or "未找到匹配文件")

    def _pure_python(self, input: GlobInput, base: Path) -> ToolResult:
        matches = list(base.glob(input.pattern))

        if input.ignore:
            filtered = []
            for m in matches:
                skip = False
                for pattern in input.ignore:
                    if _matches_ignore(str(m), pattern):
                        skip = True
                        break
                if not skip:
                    filtered.append(m)
            matches = filtered

        if input.sort_by == "modified":
            matches.sort(key=lambda f: f.stat().st_mtime if f.exists() else 0, reverse=True)
        else:
            matches.sort()

        output = "\n".join(str(m) for m in matches[:100])
        return ToolResult(output=output or "未找到匹配文件")


def _matches_glob(path_str: str, pattern: str) -> bool:
    from fnmatch import fnmatch
    return fnmatch(path_str, pattern) or fnmatch(Path(path_str).name, pattern)


def _matches_ignore(path_str: str, pattern: str) -> bool:
    from fnmatch import fnmatch
    return fnmatch(path_str, pattern) or pattern in path_str
