from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MemoryScope(str, Enum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class MemoryType(str, Enum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


@dataclass
class MemoryEntry:
    key: str
    value: str
    scope: MemoryScope
    agent_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class MemorySnapshot:
    agent_name: str
    entries: list[MemoryEntry]
    timestamp: float = field(default_factory=time.time)


MEMORY_MAX_LINES = 200
MEMORY_MAX_SIZE = 25 * 1024


class AgentMemory:
    def __init__(
        self,
        cwd: Path,
        home: Path | None = None,
        agent_name: str = "",
    ):
        self._cwd = cwd.resolve()
        self._home = home or Path.home()
        self._agent_name = agent_name
        self._store: dict[MemoryScope, dict[str, MemoryEntry]] = {
            MemoryScope.USER: {},
            MemoryScope.PROJECT: {},
            MemoryScope.LOCAL: {},
        }
        self._snapshots: list[MemorySnapshot] = []

    def read(self, key: str, scope: MemoryScope | None = None) -> str | None:
        if scope:
            entry = self._store[scope].get(key)
            return entry.value if entry else None

        for s in (MemoryScope.LOCAL, MemoryScope.PROJECT, MemoryScope.USER):
            entry = self._store[s].get(key)
            if entry:
                return entry.value
        return None

    def read_all(self, scope: MemoryScope | None = None) -> dict[str, str]:
        result: dict[str, str] = {}
        scopes = [scope] if scope else [MemoryScope.USER, MemoryScope.PROJECT, MemoryScope.LOCAL]
        for s in scopes:
            for key, entry in self._store[s].items():
                if key not in result:
                    result[key] = entry.value
        return result

    def write(self, key: str, value: str, scope: MemoryScope = MemoryScope.PROJECT) -> None:
        self._store[scope][key] = MemoryEntry(
            key=key,
            value=value,
            scope=scope,
            agent_name=self._agent_name,
        )

    def delete(self, key: str, scope: MemoryScope | None = None) -> bool:
        if scope:
            if key in self._store[scope]:
                del self._store[scope][key]
                return True
            return False

        for s in MemoryScope:
            if key in self._store[s]:
                del self._store[s][key]
                return True
        return False

    def take_snapshot(self) -> MemorySnapshot:
        entries: list[MemoryEntry] = []
        for scope_store in self._store.values():
            entries.extend(scope_store.values())
        snapshot = MemorySnapshot(
            agent_name=self._agent_name,
            entries=copy.deepcopy(entries),
        )
        self._snapshots.append(snapshot)
        return snapshot

    def restore_snapshot(self, snapshot: MemorySnapshot) -> None:
        for scope in self._store:
            self._store[scope].clear()
        for entry in snapshot.entries:
            self._store[entry.scope][entry.key] = copy.deepcopy(entry)

    def get_snapshots(self) -> list[MemorySnapshot]:
        return list(self._snapshots)

    def _get_memory_dir(self, scope: MemoryScope) -> Path:
        if scope == MemoryScope.USER:
            return self._home / ".clawscode" / "memdir"
        elif scope == MemoryScope.PROJECT:
            return self._cwd / ".clawscode" / "memdir"
        else:
            return self._cwd / "memdir"

    def _get_team_memory_dir(self, scope: MemoryScope = MemoryScope.PROJECT) -> Path:
        base = self._get_memory_dir(scope)
        return base / "team"

    def ensure_memory_dir_exists(self) -> None:
        for scope in MemoryScope:
            d = self._get_memory_dir(scope)
            d.mkdir(parents=True, exist_ok=True)

    def write_memory_file(
        self,
        name: str,
        content: str,
        memory_type: str = "project",
        description: str = "",
        scope: MemoryScope = MemoryScope.PROJECT,
    ) -> bool:
        memory_dir = self._get_memory_dir(scope)
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        filename = f"{safe_name}.md"
        filepath = memory_dir / filename

        frontmatter_lines = [
            "---",
            f"name: {name}",
            f"type: {memory_type}",
            f"description: {description or name}",
            f"agent: {self._agent_name}",
            "---",
            "",
        ]

        try:
            filepath.write_text(
                "\n".join(frontmatter_lines) + content, encoding="utf-8"
            )
            self.write(key=f"file:{name}", value=content[:500], scope=scope)
            return True
        except OSError:
            return False

    def read_memory_file(self, name: str, scope: MemoryScope = MemoryScope.PROJECT) -> str | None:
        memory_dir = self._get_memory_dir(scope)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        filepath = memory_dir / f"{safe_name}.md"
        if not filepath.exists():
            return None
        try:
            raw = filepath.read_text(encoding="utf-8")
            if raw.startswith("---"):
                end = raw.find("---", 3)
                if end != -1:
                    return raw[end + 3:].strip()
            return raw.strip()
        except (OSError, UnicodeDecodeError):
            return None

    def list_memory_files(self, scope: MemoryScope | None = None) -> list[dict]:
        scopes = [scope] if scope else list(MemoryScope)
        results = []
        for s in scopes:
            memory_dir = self._get_memory_dir(s)
            if not memory_dir.exists():
                continue
            for f in sorted(memory_dir.glob("*.md")):
                try:
                    raw = f.read_text(encoding="utf-8")
                    meta = {"name": f.stem, "scope": s.value, "path": str(f)}
                    if raw.startswith("---"):
                        end = raw.find("---", 3)
                        if end != -1:
                            header = raw[3:end].strip()
                            for line in header.split("\n"):
                                if ":" in line:
                                    k, v = line.split(":", 1)
                                    meta[k.strip()] = v.strip()
                    meta["size"] = len(raw)
                    results.append(meta)
                except (OSError, UnicodeDecodeError):
                    continue
        return results

    def load_from_memory_files(self) -> None:
        from src.services.memory import MemoryDiscovery

        discovery = MemoryDiscovery(self._cwd, self._home)
        discovered = discovery.discover_all()

        scope_map = {
            "home": MemoryScope.USER,
            "project": MemoryScope.PROJECT,
            "local": MemoryScope.LOCAL,
        }

        for path, level in discovered:
            scope = MemoryScope.PROJECT
            for prefix, s in scope_map.items():
                if level.startswith(prefix):
                    scope = s
                    break

            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    self.write(
                        key=f"memory:{path}",
                        value=content,
                        scope=scope,
                    )
            except (OSError, UnicodeDecodeError):
                continue

    def save_to_file(self, content: str, scope: MemoryScope = MemoryScope.PROJECT) -> bool:
        if scope == MemoryScope.USER:
            target_dir = self._home / ".clawscode" / "memdir"
        elif scope == MemoryScope.PROJECT:
            target_dir = self._cwd / ".clawscode" / "memdir"
        else:
            target_dir = self._cwd / "memdir"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            lines = content.split("\n")
            if len(lines) > MEMORY_MAX_LINES:
                content = "\n".join(lines[:MEMORY_MAX_LINES])
            if len(content.encode("utf-8")) > MEMORY_MAX_SIZE:
                content = content.encode("utf-8")[:MEMORY_MAX_SIZE].decode("utf-8", errors="ignore")
            target_file = target_dir / "MEMORY.md"
            target_file.write_text(content, encoding="utf-8")
            return True
        except OSError:
            return False

    def format_for_prompt(self) -> str:
        all_entries = self.read_all()
        file_entries = self.list_memory_files()

        parts = []
        if file_entries:
            parts.append("## 持久化记忆文件")
            for entry in file_entries:
                desc = entry.get("description", entry["name"])
                parts.append(f"- **{entry['name']}** ({entry['scope']}): {desc}")

        if all_entries:
            parts.append(f"\n## Agent 记忆 ({self._agent_name})")
            for key, value in all_entries.items():
                parts.append(f"- **{key}**: {value[:200]}")

        return "\n".join(parts) if parts else ""

    def write_team_memory_file(
        self,
        name: str,
        content: str,
        memory_type: str = "project",
        description: str = "",
        scope: MemoryScope = MemoryScope.PROJECT,
    ) -> bool:
        team_dir = self._get_team_memory_dir(scope)
        try:
            team_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        filepath = team_dir / f"{safe_name}.md"

        frontmatter_lines = [
            "---",
            f"name: {name}",
            f"type: {memory_type}",
            f"description: {description or name}",
            f"agent: {self._agent_name}",
            f"scope: team",
            "---",
            "",
        ]

        try:
            filepath.write_text(
                "\n".join(frontmatter_lines) + content, encoding="utf-8"
            )
            return True
        except OSError:
            return False

    def list_team_memory_files(self, scope: MemoryScope = MemoryScope.PROJECT) -> list[dict]:
        team_dir = self._get_team_memory_dir(scope)
        if not team_dir.exists():
            return []

        results = []
        for f in sorted(team_dir.glob("*.md")):
            try:
                raw = f.read_text(encoding="utf-8")
                meta = {"name": f.stem, "scope": "team", "path": str(f)}
                if raw.startswith("---"):
                    end = raw.find("---", 3)
                    if end != -1:
                        header = raw[3:end].strip()
                        for line in header.split("\n"):
                            if ":" in line:
                                k, v = line.split(":", 1)
                                meta[k.strip()] = v.strip()
                meta["size"] = len(raw)
                results.append(meta)
            except (OSError, UnicodeDecodeError):
                continue
        return results

    def save_team_memory(self, content: str, scope: MemoryScope = MemoryScope.PROJECT) -> bool:
        team_dir = self._get_team_memory_dir(scope)
        try:
            team_dir.mkdir(parents=True, exist_ok=True)
            lines = content.split("\n")
            if len(lines) > MEMORY_MAX_LINES:
                content = "\n".join(lines[:MEMORY_MAX_LINES])
            if len(content.encode("utf-8")) > MEMORY_MAX_SIZE:
                content = content.encode("utf-8")[:MEMORY_MAX_SIZE].decode("utf-8", errors="ignore")
            target_file = team_dir / "MEMORY.md"
            target_file.write_text(content, encoding="utf-8")
            return True
        except OSError:
            return False


def memory_age(file_path: Path) -> str:
    import os
    try:
        mtime = os.path.getmtime(str(file_path))
        age_seconds = time.time() - mtime
        age_days = int(age_seconds / 86400)
        if age_days == 0:
            return "today"
        elif age_days == 1:
            return "yesterday"
        elif age_days < 30:
            return f"{age_days} days ago"
        elif age_days < 365:
            return f"{age_days // 30} months ago"
        else:
            return f"{age_days // 365} years ago"
    except OSError:
        return "unknown"


def memory_freshness_text(file_path: Path) -> str:
    age = memory_age(file_path)
    if age in ("today", "yesterday", "unknown"):
        return ""
    return f"(This memory is {age})"


def memory_freshness_note(file_path: Path) -> str:
    text = memory_freshness_text(file_path)
    if not text:
        return ""
    return f"<system-reminder>{text}</system-reminder>"
