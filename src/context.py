from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from src.tool import Tool


def build_system_prompt(cwd: Path, tools: list[Tool]) -> str:
    parts = [
        "你是一个 AI 编程助手。用户会与你对话，你需要通过工具完成编程任务。",
        f"\n当前工作目录：{cwd}",
    ]

    claude_md = cwd / "CLAUDE.md"
    if claude_md.exists():
        parts.append(f"\n项目说明（CLAUDE.md）：\n{claude_md.read_text()}")

    try:
        git_status = subprocess.run(
            ["git", "status", "--short"], cwd=cwd, capture_output=True, text=True
        )
        if git_status.returncode == 0 and git_status.stdout.strip():
            parts.append(f"\nGit 状态：\n{git_status.stdout}")
    except Exception:
        pass

    return "\n".join(parts)
