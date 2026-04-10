from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class BashInput(BaseModel):
    command: str = Field(description="要执行的 Shell 命令")
    timeout: int | None = Field(default=None, description="超时秒数")
    cwd: str | None = Field(default=None, description="工作目录")


class BashTool(Tool):
    name = "Bash"
    description = "执行 Shell 命令并返回输出"
    input_schema = BashInput

    async def call(self, input: BashInput, context: Any) -> ToolResult:
        proc = await asyncio.create_subprocess_shell(
            input.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=input.cwd or context.cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=input.timeout or 120
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(output="命令超时", is_error=True)
        output = stdout.decode(errors="replace")
        if proc.returncode != 0:
            output += f"\nSTDERR: {stderr.decode(errors='replace')}"
        return ToolResult(output=output, is_error=proc.returncode != 0)
