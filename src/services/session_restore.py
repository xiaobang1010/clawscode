from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.services.session_storage import SessionData, SessionStorage


@dataclass
class RestoredSession:
    session_data: SessionData
    messages: list[dict]
    metadata: dict[str, Any]


class SessionRestore:
    def __init__(self, storage: SessionStorage | None = None, home: Path | None = None):
        self._storage = storage or SessionStorage(home=home)

    def restore(self, session_id: str) -> RestoredSession | None:
        session = self._storage.load(session_id)
        if session is None:
            return None

        messages = self._rebuild_messages(session)
        metadata = self._rebuild_metadata(session)

        return RestoredSession(
            session_data=session,
            messages=messages,
            metadata=metadata,
        )

    def restore_latest(self) -> RestoredSession | None:
        sessions = self._storage.list_sessions()
        if not sessions:
            return None
        return self.restore(sessions[0].session_id)

    def list_recent(self, limit: int = 10) -> list[SessionData]:
        sessions = self._storage.list_sessions()
        return sessions[:limit]

    def _rebuild_messages(self, session: SessionData) -> list[dict]:
        messages = []
        for msg in session.messages:
            if isinstance(msg, dict) and "role" in msg:
                messages.append(msg)
        return messages

    def _rebuild_metadata(self, session: SessionData) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "message_count": len(session.messages),
            **session.metadata,
        }
