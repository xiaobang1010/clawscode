from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

_KWARGS = dict(capture_output=True, encoding="utf-8", errors="replace")


def create_worktree(
    cwd: Path,
    branch_name: str | None = None,
    base_ref: str = "HEAD",
) -> Path | None:
    if not branch_name:
        branch_name = f"clawscode-agent-{uuid.uuid4().hex[:8]}"

    worktree_dir = cwd / ".git-worktrees" / branch_name

    try:
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), base_ref],
            **_KWARGS,
            cwd=str(cwd),
        )

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            **_KWARGS,
            cwd=str(worktree_dir),
        )
        if result.returncode == 0 and result.stdout:
            return Path(result.stdout.strip())
        return worktree_dir
    except Exception:
        return None


def remove_worktree(cwd: Path, worktree_dir: Path, force: bool = False) -> bool:
    try:
        cmd = ["git", "worktree", "remove", str(worktree_dir)]
        if force:
            cmd.append("--force")

        r = subprocess.run(cmd, **_KWARGS, cwd=str(cwd))
        if r.returncode != 0 and force:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_dir)],
                **_KWARGS,
                cwd=str(cwd),
            )

        branch_name = worktree_dir.name
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            **_KWARGS,
            cwd=str(cwd),
        )
        return True
    except Exception:
        return False


def list_worktrees(cwd: Path) -> list[dict]:
    try:
        r = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            **_KWARGS,
            cwd=str(cwd),
        )
        if r.returncode != 0:
            return []

        worktrees = []
        current: dict = {}
        for line in r.stdout.strip().split("\n"):
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
                continue
            if line.startswith("worktree "):
                current["path"] = line[len("worktree "):]
            elif line.startswith("HEAD "):
                current["head"] = line[len("HEAD "):]
            elif line.startswith("branch "):
                current["branch"] = line[len("branch "):]
        if current:
            worktrees.append(current)
        return worktrees
    except Exception:
        return []


def get_worktree_for_agent(cwd: Path, agent_name: str) -> Path | None:
    branch_name = f"clawscode-agent-{agent_name}"
    worktrees = list_worktrees(cwd)
    for wt in worktrees:
        if wt.get("branch", "").endswith(branch_name):
            return Path(wt["path"])
    return None


class WorktreeIsolation:
    def __init__(self, cwd: Path, agent_name: str = ""):
        self._cwd = cwd
        self._agent_name = agent_name or uuid.uuid4().hex[:8]
        self._worktree_dir: Path | None = None
        self._original_cwd = cwd

    @property
    def worktree_dir(self) -> Path | None:
        return self._worktree_dir

    def __enter__(self) -> WorktreeIsolation:
        self._worktree_dir = create_worktree(
            self._cwd, branch_name=f"clawscode-agent-{self._agent_name}"
        )
        return self

    def __exit__(self, *args) -> None:
        if self._worktree_dir is not None:
            remove_worktree(self._cwd, self._worktree_dir, force=True)
            self._worktree_dir = None
