from __future__ import annotations

import asyncio
import os
import re
import shlex
import uuid
from dataclasses import dataclass, field
from pathlib import Path
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


@dataclass
class BackgroundTask:
    task_id: str
    command: str
    process: asyncio.subprocess.Process | None = None
    output: str = ""
    error: str = ""
    is_running: bool = True
    exit_code: int | None = None


class BackgroundTaskTracker:
    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}

    def create_task(self, command: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        self._tasks[task_id] = BackgroundTask(
            task_id=task_id,
            command=command,
        )
        return task_id

    def get_task(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs: Any) -> None:
        task = self._tasks.get(task_id)
        if task:
            for k, v in kwargs.items():
                setattr(task, k, v)

    def remove_task(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    def list_tasks(self) -> list[dict]:
        return [
            {
                "task_id": t.task_id,
                "command": t.command[:80],
                "is_running": t.is_running,
                "exit_code": t.exit_code,
            }
            for t in self._tasks.values()
        ]


_background_tracker = BackgroundTaskTracker()


def get_background_tracker() -> BackgroundTaskTracker:
    return _background_tracker


_SIXEL_START = re.compile(rb"\x1bPq")
_SIXEL_END = re.compile(rb"\x1b\\")
_ITERM2_START = re.compile(rb"\x1b]1337;")
_KITTY_START = re.compile(rb"\x1b_G")


def is_image_output(output: bytes) -> bool:
    if _SIXEL_START.search(output):
        return True
    if _ITERM2_START.search(output):
        return True
    if _KITTY_START.search(output):
        return True
    return False


def apply_sed_edit(command: str, cwd: str) -> dict | None:
    sed_match = re.match(
        r"sed\s+(?:-i\s+)?(?:-e\s+)?['\"]?s/([^/]*)/([^/]*)/([gi]*)['\"]?\s+(\S+)",
        command,
    )
    if not sed_match:
        return None

    pattern = sed_match.group(1)
    replacement = sed_match.group(2)
    flags = sed_match.group(3)
    target_file = sed_match.group(4)

    if target_file.startswith("-"):
        return None

    file_path = Path(cwd) / target_file
    if not file_path.exists():
        return None

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    try:
        regex_flags = 0
        if "i" in flags:
            regex_flags |= re.IGNORECASE

        matches = list(re.finditer(pattern, content, regex_flags))
        if not matches:
            return None

        new_content = re.sub(pattern, replacement, content, count=0 if "g" in flags else 1, flags=regex_flags)

        diff_lines = []
        old_lines = content.splitlines()
        new_lines = new_content.splitlines()
        for i, (old, new) in enumerate(zip(old_lines, new_lines)):
            if old != new:
                diff_lines.append({"line": i + 1, "old": old, "new": new})

        return {
            "file": str(file_path),
            "pattern": pattern,
            "replacement": replacement,
            "matches": len(matches),
            "preview": diff_lines[:10],
            "new_content": new_content,
        }
    except re.error:
        return None


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

    image_detected = is_image_output(stdout)

    output = stdout.decode(errors="replace")
    if proc.returncode != 0:
        output += f"\nSTDERR: {stderr.decode(errors='replace')}"

    metadata = {}
    if image_detected:
        metadata["is_image"] = True

    return ToolResult(
        output=output,
        is_error=proc.returncode != 0,
        metadata=metadata,
    )


async def run_in_background(
    command: str, cwd: str, env: dict[str, str]
) -> str:
    tracker = get_background_tracker()
    task_id = tracker.create_task(command)

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    tracker.update_task(task_id, process=proc)

    async def _watch():
        stdout, stderr = await proc.communicate()
        tracker.update_task(
            task_id,
            output=stdout.decode(errors="replace"),
            error=stderr.decode(errors="replace"),
            is_running=False,
            exit_code=proc.returncode,
        )

    asyncio.create_task(_watch())
    return task_id
