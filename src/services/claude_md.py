from __future__ import annotations

from pathlib import Path

CLAUDE_MD_FILENAME = "CLAUDE.md"
CLAWSCODE_DIR_NAME = ".clawscode"


class ClaudeMdDiscovery:
    def __init__(self, cwd: Path, home: Path | None = None):
        self._cwd = cwd.resolve()
        self._home = home or Path.home()

    def discover_all(self) -> list[tuple[Path, str]]:
        results: list[tuple[Path, str]] = []

        home_md = self._home / CLAUDE_MD_FILENAME
        if home_md.exists() and home_md.is_file():
            results.append((home_md, "home"))

        home_clawscode = self._home / CLAWSCODE_DIR_NAME / CLAUDE_MD_FILENAME
        if home_clawscode.exists() and home_clawscode.is_file():
            results.append((home_clawscode, "home_clawscode"))

        project_root_md = self._cwd / CLAUDE_MD_FILENAME
        if project_root_md.exists() and project_root_md.is_file():
            results.append((project_root_md, "project_root"))

        project_clawscode_md = self._cwd / CLAWSCODE_DIR_NAME / CLAUDE_MD_FILENAME
        if project_clawscode_md.exists() and project_clawscode_md.is_file():
            results.append((project_clawscode_md, "project_clawscode"))

        for parent in self._cwd.parents:
            md_file = parent / CLAUDE_MD_FILENAME
            if md_file.exists() and md_file.is_file():
                if (md_file, "project_root") not in results:
                    results.append((md_file, f"parent:{md_file.parent.name}"))

        return results

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
        return f"\n## 项目说明（CLAUDE.md）\n\n{merged}"
