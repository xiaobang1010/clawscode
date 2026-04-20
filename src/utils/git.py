from __future__ import annotations

import subprocess
from pathlib import Path

_KWARGS = dict(capture_output=True, encoding="utf-8", errors="replace")


def is_git_repo(cwd: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            **_KWARGS,
            cwd=str(cwd),
        )
        return r.returncode == 0 and r.stdout is not None and r.stdout.strip() == "true"
    except Exception:
        return False


def has_changes(cwd: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            **_KWARGS,
            cwd=str(cwd),
        )
        return r.returncode == 0 and r.stdout is not None and bool(r.stdout.strip())
    except Exception:
        return False


def create_checkpoint(cwd: Path, index: int) -> bool:
    try:
        subprocess.run(
            ["git", "add", "-A"],
            **_KWARGS,
            cwd=str(cwd),
        )
        r = subprocess.run(
            ["git", "commit", "-m", f"clawscode: checkpoint #{index}"],
            **_KWARGS,
            cwd=str(cwd),
        )
        return r.returncode == 0
    except Exception:
        return False


def undo_checkpoint(cwd: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            **_KWARGS,
            cwd=str(cwd),
        )
        return r.returncode == 0
    except Exception:
        return False


def undo_all_checkpoints(cwd: Path, count: int) -> bool:
    try:
        r = subprocess.run(
            ["git", "reset", "--hard", f"HEAD~{count}"],
            **_KWARGS,
            cwd=str(cwd),
        )
        return r.returncode == 0
    except Exception:
        return False


def get_diff(cwd: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            **_KWARGS,
            cwd=str(cwd),
        )
        if r.returncode != 0 or not r.stdout:
            return None
        diff = r.stdout.strip()
        return diff if diff else None
    except Exception:
        return None


def get_checkpoint_log(cwd: Path, count: int) -> list[dict]:
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", f"-{count}"],
            **_KWARGS,
            cwd=str(cwd),
        )
        if r.returncode != 0 or not r.stdout:
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
