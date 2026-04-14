from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "format ",
    "del /s ", "del /f ", "rmdir /s", "> /dev/sd",
    "shutdown", "reboot", "init 0", "init 6",
    ":(){:|:&};:", "fork bomb",
]


class BashInput(BaseModel):
    command: str = Field(description="要执行的 Shell 命令")
    timeout: int | None = Field(default=None, description="超时秒数")
    cwd: str | None = Field(default=None, description="工作目录")
    env: dict[str, str] | None = Field(default=None, description="环境变量")


class BashTool(Tool):
    name = "Bash"
    description = "执行 Shell 命令并返回输出。支持多命令、工作目录指定和环境变量注入。"
    input_schema = BashInput

    async def call(self, input: BashInput, context: Any) -> ToolResult:
        work_dir = input.cwd or str(context.cwd)

        env = os.environ.copy()
        if input.env:
            env.update(input.env)

        commands = _split_commands(input.command)
        all_output = []
        for cmd in commands:
            result = await _run_single(cmd, work_dir, env, input.timeout or 120)
            all_output.append(result)
            if result.is_error:
                break

        return ToolResult(
            output="\n".join(r.output for r in all_output),
            is_error=any(r.is_error for r in all_output),
        )


def _split_commands(command: str) -> list[str]:
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        return [command]

    commands = []
    current = []
    for part in parts:
        if part in ("&&", "||", ";"):
            if current:
                commands.append(" ".join(current))
                current = []
        else:
            current.append(part)
    if current:
        commands.append(" ".join(current))

    return commands if commands else [command]


async def _run_single(
    command: str, cwd: str, env: dict[str, str], timeout: int
) -> ToolResult:
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return ToolResult(output=f"命令超时 ({timeout}s): {command[:80]}", is_error=True)

    output = stdout.decode(errors="replace")
    if proc.returncode != 0:
        output += f"\nSTDERR: {stderr.decode(errors='replace')}"
    return ToolResult(output=output, is_error=proc.returncode != 0)
