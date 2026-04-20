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
            target_file = target_dir / "MEMORY.md"
            target_file.write_text(content, encoding="utf-8")
            return True
        except OSError:
            return False

    def format_for_prompt(self) -> str:
        all_entries = self.read_all()
        if not all_entries:
            return ""
        lines = [f"## Agent 记忆 ({self._agent_name})"]
        for key, value in all_entries.items():
            lines.append(f"- **{key}**: {value[:200]}")
        return "\n".join(lines)
