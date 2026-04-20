from __future__ import annotations

from pathlib import Path

MEMORY_FILENAME = "MEMORY.md"
MEMORY_DIR_NAME = "memdir"
CLAWSCODE_DIR_NAME = ".clawscode"


class MemoryDiscovery:
    def __init__(self, cwd: Path, home: Path | None = None, memdir: str = "", search_nested: bool = True):
        self._cwd = cwd.resolve()
        self._home = home or Path.home()
        self._memdir_name = memdir or MEMORY_DIR_NAME
        self._search_nested = search_nested

    def discover_all(self) -> list[tuple[Path, str]]:
        results: list[tuple[Path, str]] = []

        home_memory = self._home / CLAWSCODE_DIR_NAME / self._memdir_name / MEMORY_FILENAME
        if home_memory.exists() and home_memory.is_file():
            results.append((home_memory, "home"))

        project_memory = self._cwd / CLAWSCODE_DIR_NAME / self._memdir_name / MEMORY_FILENAME
        if project_memory.exists() and project_memory.is_file():
            results.append((project_memory, "project"))

        local_memory = self._cwd / self._memdir_name / MEMORY_FILENAME
        if local_memory.exists() and local_memory.is_file():
            results.append((local_memory, "local"))

        if self._search_nested:
            results.extend(self._discover_nested(self._cwd))

        return results

    def _discover_nested(self, base: Path) -> list[tuple[Path, str]]:
        nested: list[tuple[Path, str]] = []
        try:
            for item in sorted(base.rglob(MEMORY_FILENAME)):
                if item.is_file() and item not in [r[0] for r in nested]:
                    rel = item.relative_to(self._cwd)
                    nested.append((item, f"nested:{rel}"))
        except (OSError, ValueError):
            pass
        return nested

    def load_merged(self) -> str:
        discovered = self.discover_all()
        if not discovered:
            return ""

        parts: list[str] = []
        for path, level in discovered:
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"--- {level} ({path}) ---\n{content}")
            except (OSError, UnicodeDecodeError):
                continue

        return "\n\n".join(parts)

    def load_for_system_prompt(self) -> str:
        merged = self.load_merged()
        if not merged:
            return ""
        return f"\n## 记忆（MEMORY.md）\n\n{merged}"
