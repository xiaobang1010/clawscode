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

    def _classify_memory_type(self, content: str) -> str:
        lower = content.lower()
        if any(kw in lower for kw in ["用户偏好", "偏好", "习惯", "user preference"]):
            return "user"
        if any(kw in lower for kw in ["用户反馈", "反馈", "feedback", "不要", "避免"]):
            return "feedback"
        if any(kw in lower for kw in ["项目", "架构", "技术栈", "project", "architecture"]):
            return "project"
        return "reference"

    def load_merged(self) -> str:
        from src.agents.memory import memory_freshness_note
        discovered = self.discover_all()
        if not discovered:
            return ""

        parts: list[str] = []
        for path, level in discovered:
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    freshness = memory_freshness_note(path)
                    parts.append(f"--- {level} ({path}) ---\n{content}")
                    if freshness:
                        parts.append(freshness)
            except (OSError, UnicodeDecodeError):
                continue

        return "\n\n".join(parts)

    def load_for_system_prompt(self) -> str:
        merged = self.load_merged()
        if not merged:
            return ""

        memory_type = self._classify_memory_type(merged)
        type_labels = {
            "user": "用户偏好",
            "feedback": "用户反馈",
            "project": "项目上下文",
            "reference": "参考信息",
        }
        type_label = type_labels.get(memory_type, "参考信息")

        return f"\n## 记忆（MEMORY.md）[类型: {type_label}]\n\n{merged}"
