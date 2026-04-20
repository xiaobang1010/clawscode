# Git 工具函数
from __future__ import annotations

import subprocess
from pathlib import Path


def is_git_repo(cwd: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def has_changes(cwd: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def create_checkpoint(cwd: Path, index: int) -> bool:
    try:
        subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        r = subprocess.run(
            ["git", "commit", "-m", f"clawscode: checkpoint #{index}"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        return r.returncode == 0
    except Exception:
        return False


def undo_checkpoint(cwd: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        return r.returncode == 0
    except Exception:
        return False


def undo_all_checkpoints(cwd: Path, count: int) -> bool:
    try:
        r = subprocess.run(
            ["git", "reset", "--hard", f"HEAD~{count}"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        return r.returncode == 0
    except Exception:
        return False


def get_diff(cwd: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        if r.returncode != 0:
            return None
        diff = r.stdout.strip()
        return diff if diff else None
    except Exception:
        return None


def get_checkpoint_log(cwd: Path, count: int) -> list[dict]:
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", f"-{count}"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        if r.returncode != 0:
            return []
        result = []
        for line in r.stdout.strip().splitlines():
            if not line.startswith("clawscode: checkpoint"):
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            result.append({"hash": parts[0], "message": parts[1]})
        return result
    except Exception:
        return []
