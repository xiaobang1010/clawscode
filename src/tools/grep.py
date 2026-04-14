from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class GrepInput(BaseModel):
    pattern: str = Field(description="搜索的正则表达式")
    path: str | None = Field(default=None, description="搜索目录")
    file_glob: str | None = Field(default=None, description="文件过滤，如 *.py")
    output_mode: str = Field(default="content", description="输出模式: content/files_with_matches/count")
    context_lines: int = Field(default=0, description="上下文行数")
    head_limit: int | None = Field(default=100, description="最大输出行数")


class GrepTool(Tool):
    name = "Grep"
    description = "在文件内容中搜索正则表达式。支持输出模式切换、上下文行数、ripgrep 加速。"
    input_schema = GrepInput
    is_readonly = True

    async def call(self, input: GrepInput, context: Any) -> ToolResult:
        base = Path(input.path or context.cwd)

        if shutil.which("rg"):
            return await self._ripgrep(input, base)

        return await self._pure_python(input, base)

    async def _ripgrep(self, input: GrepInput, base: Path) -> ToolResult:
        cmd = ["rg", "--no-heading", "--with-filename", "--line-number"]
        if input.output_mode == "files_with_matches":
            cmd.append("-l")
        elif input.output_mode == "count":
            cmd.append("-c")
        if input.context_lines > 0:
            cmd.extend(["-C", str(input.context_lines)])
        if input.file_glob:
            cmd.extend(["--glob", input.file_glob])
        if input.head_limit:
            cmd.extend(["-m", str(input.head_limit)])
        cmd.extend(["--color", "never", input.pattern, str(base)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        output = stdout.decode(errors="replace").strip()
        if not output:
            return ToolResult(output="未找到匹配内容")
        return ToolResult(output=output)

    async def _pure_python(self, input: GrepInput, base: Path) -> ToolResult:
        if input.output_mode == "files_with_matches":
            return self._search_files(input, base)
        elif input.output_mode == "count":
            return self._search_count(input, base)

        results: list[str] = []
        files = base.glob(input.file_glob or "**/*")
        for f in files:
            if f.is_file():
                try:
                    file_lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                    for i, line in enumerate(file_lines):
                        if re.search(input.pattern, line):
                            start = max(0, i - input.context_lines)
                            end = min(len(file_lines), i + input.context_lines + 1)
                            for j in range(start, end):
                                prefix = ">" if j == i else " "
                                results.append(f"{prefix}{f}:{j + 1}: {file_lines[j].strip()}")
                except Exception:
                    pass
                if len(results) >= (input.head_limit or 100):
                    break

        output = "\n".join(results[: input.head_limit or 100])
        return ToolResult(output=output or "未找到匹配内容")

    def _search_files(self, input: GrepInput, base: Path) -> ToolResult:
        matched_files: list[str] = []
        files = base.glob(input.file_glob or "**/*")
        for f in files:
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    if re.search(input.pattern, text):
                        matched_files.append(str(f))
                except Exception:
                    pass
                if len(matched_files) >= (input.head_limit or 100):
                    break
        return ToolResult(output="\n".join(matched_files) or "未找到匹配文件")

    def _search_count(self, input: GrepInput, base: Path) -> ToolResult:
        counts: list[str] = []
        files = base.glob(input.file_glob or "**/*")
        for f in files:
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    c = len(re.findall(input.pattern, text))
                    if c > 0:
                        counts.append(f"{f}: {c}")
                except Exception:
                    pass
                if len(counts) >= (input.head_limit or 100):
                    break
        return ToolResult(output="\n".join(counts) or "未找到匹配内容")
