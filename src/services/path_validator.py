from __future__ import annotations

import os
from pathlib import Path


class PathValidator:
    def __init__(self, cwd: Path, additional_dirs: list[Path] | None = None):
        self._cwd = cwd.resolve()
        self._allowed_dirs: list[Path] = [self._cwd]
        if additional_dirs:
            for d in additional_dirs:
                resolved = d.resolve()
                if resolved not in self._allowed_dirs:
                    self._allowed_dirs.append(resolved)

    def is_path_allowed(self, path: str | Path) -> bool:
        resolved = self._resolve_path(path)
        return self._is_under_allowed_dir(resolved)

    def normalize_path(self, path: str | Path) -> Path:
        return self._resolve_path(path)

    def validate_path(self, path: str | Path) -> tuple[bool, str]:
        try:
            resolved = self._resolve_path(path)
        except (OSError, ValueError) as e:
            return False, f"无效路径: {e}"

        if not self._is_under_allowed_dir(resolved):
            return False, f"路径不在允许的目录范围内: {resolved}"

        return True, str(resolved)

    def add_allowed_dir(self, directory: str | Path) -> None:
        resolved = Path(directory).resolve()
        if resolved not in self._allowed_dirs:
            self._allowed_dirs.append(resolved)

    def get_allowed_dirs(self) -> list[Path]:
        return list(self._allowed_dirs)

    def make_relative(self, path: str | Path) -> str:
        try:
            resolved = self._resolve_path(path)
            return str(resolved.relative_to(self._cwd))
        except ValueError:
            return str(resolved)

    def _resolve_path(self, path: str | Path) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self._cwd / p

        resolved = p.resolve()

        if os.name == "nt":
            resolved_str = str(resolved)
            resolved = Path(resolved_str)

        return resolved

    def _is_under_allowed_dir(self, path: Path) -> bool:
        for allowed in self._allowed_dirs:
            try:
                path.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False
