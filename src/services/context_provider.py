from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path


@dataclass
class GitContext:
    branch: str = ""
    recent_commits: list[str] = field(default_factory=list)
    user_name: str = ""
    user_email: str = ""
    remote_url: str = ""
    is_repo: bool = False
    has_changes: bool = False
    changed_files: list[str] = field(default_factory=list)


@dataclass
class EnvironmentInfo:
    os_name: str = ""
    os_version: str = ""
    shell: str = ""
    python_version: str = ""
    date: str = ""
    cwd: str = ""
    directory_listing: str = ""
    git: GitContext = field(default_factory=GitContext)


class ContextProvider:
    def __init__(self, cwd: Path):
        self._cwd = cwd
        self._cache: dict[str, str] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._cache_ttl = 60.0

    def get_environment_info(self) -> EnvironmentInfo:
        return EnvironmentInfo(
            os_name=platform.system(),
            os_version=platform.release(),
            shell=self._detect_shell(),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            date=datetime.now().strftime("%Y-%m-%d"),
            cwd=str(self._cwd),
            directory_listing=self._get_directory_listing(),
            git=self._get_git_context(),
        )

    def format_environment_info(self, env: EnvironmentInfo | None = None) -> str:
        if env is None:
            env = self.get_environment_info()

        parts = [
            f"当前工作目录：{env.cwd}",
            f"操作系统：{env.os_name} {env.os_version}",
            f"Shell：{env.shell}",
            f"Python：{env.python_version}",
            f"日期：{env.date}",
        ]

        if env.directory_listing:
            parts.append(f"\n目录结构：\n{env.directory_listing}")

        if env.git.is_repo:
            parts.append(f"\nGit 分支：{env.git.branch}")
            if env.git.user_name:
                parts.append(f"Git 用户：{env.git.user_name} <{env.git.user_email}>")
            if env.git.remote_url:
                parts.append(f"远程仓库：{env.git.remote_url}")
            if env.git.recent_commits:
                parts.append("\n最近提交：")
                for commit in env.git.recent_commits:
                    parts.append(f"  {commit}")
            if env.git.has_changes:
                parts.append(f"\n未提交的更改：")
                for f in env.git.changed_files[:20]:
                    parts.append(f"  {f}")

        return "\n".join(parts)

    def get_cached_context(self, key: str, force_refresh: bool = False) -> str | None:
        now = time.monotonic()
        if not force_refresh and key in self._cache:
            ts = self._cache_timestamps.get(key, 0)
            if now - ts < self._cache_ttl:
                return self._cache[key]
        return None

    def set_cached_context(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._cache_timestamps[key] = time.monotonic()

    def invalidate_cache(self, key: str | None = None) -> None:
        if key is None:
            self._cache.clear()
            self._cache_timestamps.clear()
        else:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)

    def _detect_shell(self) -> str:
        if platform.system() == "Windows":
            comspec = os.environ.get("COMSPEC", "")
            if "powershell" in comspec.lower() or "pwsh" in comspec.lower():
                return comspec
            return "cmd.exe"
        return os.environ.get("SHELL", "/bin/bash")

    def _get_directory_listing(self) -> str:
        try:
            entries = sorted(self._cwd.iterdir())
            lines = []
            for entry in entries[:50]:
                name = entry.name
                if entry.is_dir():
                    lines.append(f"  {name}/")
                else:
                    lines.append(f"  {name}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _get_git_context(self) -> GitContext:
        ctx = GitContext()

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self._cwd, capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return ctx
            ctx.is_repo = True

            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self._cwd, capture_output=True, text=True, timeout=5,
            )
            if branch_result.returncode == 0:
                ctx.branch = branch_result.stdout.strip()

            log_result = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                cwd=self._cwd, capture_output=True, text=True, timeout=5,
            )
            if log_result.returncode == 0:
                ctx.recent_commits = [
                    line.strip() for line in log_result.stdout.strip().split("\n") if line.strip()
                ]

            user_result = subprocess.run(
                ["git", "config", "user.name"],
                cwd=self._cwd, capture_output=True, text=True, timeout=5,
            )
            if user_result.returncode == 0:
                ctx.user_name = user_result.stdout.strip()

            email_result = subprocess.run(
                ["git", "config", "user.email"],
                cwd=self._cwd, capture_output=True, text=True, timeout=5,
            )
            if email_result.returncode == 0:
                ctx.user_email = email_result.stdout.strip()

            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self._cwd, capture_output=True, text=True, timeout=5,
            )
            if remote_result.returncode == 0:
                ctx.remote_url = remote_result.stdout.strip()

            status_result = subprocess.run(
                ["git", "status", "--short"],
                cwd=self._cwd, capture_output=True, text=True, timeout=5,
            )
            if status_result.returncode == 0 and status_result.stdout.strip():
                ctx.has_changes = True
                ctx.changed_files = [
                    line.strip() for line in status_result.stdout.strip().split("\n") if line.strip()
                ]

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        return ctx
