from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.services.session_storage import SessionData, SessionStorage


@dataclass
class RestoredSession:
    session_data: SessionData
    messages: list[dict]
    metadata: dict[str, Any]
    file_history: list[str] = field(default_factory=list)
    todo_list: list[dict] = field(default_factory=list)
    agent_type: str = ""
    model_override: str = ""


class SessionRestore:
    def __init__(self, storage: SessionStorage | None = None, home: Path | None = None):
        self._storage = storage or SessionStorage(home=home)

    def restore(self, session_id: str) -> RestoredSession | None:
        session = self._storage.load(session_id)
        if session is None:
            return None

        messages = self._rebuild_messages(session)
        metadata = self._rebuild_metadata(session)
        file_history = self._restore_file_history(session)
        todo_list = self._restore_todo_list(session)
        agent_type, model_override = self._restore_agent_config(session)

        return RestoredSession(
            session_data=session,
            messages=messages,
            metadata=metadata,
            file_history=file_history,
            todo_list=todo_list,
            agent_type=agent_type,
            model_override=model_override,
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
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role not in ("system", "user", "assistant", "tool"):
                continue
            if role == "system" and not msg.get("content"):
                continue
            if role == "tool" and not msg.get("tool_call_id"):
                continue
            if role in ("user", "assistant") and not msg.get("content") and not msg.get("tool_calls"):
                continue
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

    def _restore_file_history(self, session: SessionData) -> list[str]:
        history = session.metadata.get("file_history", [])
        if isinstance(history, list):
            return [str(f) for f in history if isinstance(f, (str, Path))]
        return []

    def _restore_todo_list(self, session: SessionData) -> list[dict]:
        todos = session.metadata.get("todo_list", [])
        if isinstance(todos, list):
            valid = []
            for t in todos:
                if isinstance(t, dict) and "content" in t:
                    valid.append(t)
            return valid
        return []

    def _restore_agent_config(self, session: SessionData) -> tuple[str, str]:
        agent_type = session.metadata.get("agent_type", "")
        model_override = session.metadata.get("model_override", "")
        return str(agent_type), str(model_override)

    def extract_last_todos_from_messages(self, session: SessionData) -> list[dict]:
        for msg in reversed(session.messages):
            if not isinstance(msg, dict):
                continue
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                continue
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function", {})
                if fn.get("name") == "TodoWrite":
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                        todos = args.get("todos", [])
                        if isinstance(todos, list) and todos:
                            return todos
                    except (json.JSONDecodeError, KeyError):
                        continue
        return []
