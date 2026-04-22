from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


SESSIONS_DIR_NAME = "sessions"
CLAWSCODE_DIR_NAME = ".clawscode"
SESSION_FILE_SUFFIX = ".json"


class SessionData:
    def __init__(
        self,
        session_id: str | None = None,
        title: str = "",
        created_at: str | None = None,
        updated_at: str | None = None,
        messages: list[dict] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.title = title
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.messages = messages or []
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": self.messages,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionData:
        return cls(
            session_id=data.get("session_id"),
            title=data.get("title", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            messages=data.get("messages", []),
            metadata=data.get("metadata", {}),
        )


class SessionStorage:
    def __init__(self, home: Path | None = None, storage_path: str = ""):
        if storage_path:
            self._sessions_dir = Path(storage_path)
        else:
            self._home = home or Path.home()
            self._sessions_dir = self._home / CLAWSCODE_DIR_NAME / SESSIONS_DIR_NAME
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: SessionData) -> Path:
        session.updated_at = datetime.now().isoformat()
        path = self._get_session_path(session.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = session.to_dict()
        content = json.dumps(data, indent=2, ensure_ascii=False)
        path.write_text(content, encoding="utf-8")

        return path

    def save_incremental(self, session: SessionData, new_messages: list[dict]) -> Path:
        session.messages.extend(new_messages)
        return self.save(session)

    def load(self, session_id: str) -> SessionData | None:
        path = self._get_session_path(session_id)
        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return SessionData.from_dict(data)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None

    def list_sessions(self) -> list[SessionData]:
        sessions: list[SessionData] = []
        for path in sorted(self._sessions_dir.glob(f"*{SESSION_FILE_SUFFIX}")):
            try:
                content = path.read_text(encoding="utf-8")
                data = json.loads(content)
                session = SessionData.from_dict(data)
                sessions.append(session)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def delete(self, session_id: str) -> bool:
        path = self._get_session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_session_path(self, session_id: str) -> Path:
        return self._get_session_path(session_id)

    def _get_session_path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self._sessions_dir / f"{safe_id}{SESSION_FILE_SUFFIX}"


class AutoSaveManager:
    def __init__(self, storage: SessionStorage, interval: int = 60):
        self._storage = storage
        self._interval = interval
        self._session: SessionData | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def set_session(self, session: SessionData) -> None:
        self._session = session

    async def start(self) -> None:
        if self._interval <= 0:
            return
        self._task = asyncio.create_task(self._auto_save_loop())

    async def _auto_save_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.save_now()

    async def save_now(self) -> None:
        if self._session is None:
            return
        async with self._lock:
            try:
                self._storage.save(self._session)
            except Exception:
                pass

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.save_now()
