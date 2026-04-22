from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .message_uuid import generate_uuid, MessageChain


@dataclass
class SidechainSession:
    agent_id: str
    session_id: str = field(default_factory=generate_uuid)
    parent_session_id: str | None = None
    parent_message_uuid: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "parent_message_uuid": self.parent_message_uuid,
            "created_at": self.created_at,
            "messages": self.messages,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SidechainSession:
        return cls(
            agent_id=data.get("agent_id", ""),
            session_id=data.get("session_id", generate_uuid()),
            parent_session_id=data.get("parent_session_id"),
            parent_message_uuid=data.get("parent_message_uuid"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            messages=data.get("messages", []),
            metadata=data.get("metadata", {}),
        )


class SidechainStorage:
    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or Path.home() / ".clawscode" / "sidechains"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def record_sidechain_transcript(
        self,
        messages: list[dict[str, Any]],
        agent_id: str,
        parent_session_id: str | None = None,
        parent_message_uuid: str | None = None,
    ) -> str:
        chain = MessageChain()
        chain.rebuild_chain(messages)

        for msg in chain.messages:
            msg["is_sidechain"] = True
            msg["agent_id"] = agent_id

        session = SidechainSession(
            agent_id=agent_id,
            parent_session_id=parent_session_id,
            parent_message_uuid=parent_message_uuid,
            messages=chain.messages,
        )

        path = self._get_sidechain_path(session.session_id)
        self._save_session(session, path)

        return session.session_id

    def load_sidechain_content(self, session_id: str) -> list[dict[str, Any]] | None:
        path = self._get_sidechain_path(session_id)
        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            session = SidechainSession.from_dict(data)
            return session.messages
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None

    def get_sidechain_session(self, session_id: str) -> SidechainSession | None:
        path = self._get_sidechain_path(session_id)
        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return SidechainSession.from_dict(data)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None

    def list_sidechains_for_agent(self, agent_id: str) -> list[SidechainSession]:
        sessions = []
        for path in self._base_dir.glob("*.json"):
            try:
                content = path.read_text(encoding="utf-8")
                data = json.loads(content)
                session = SidechainSession.from_dict(data)
                if session.agent_id == agent_id:
                    sessions.append(session)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue

        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions

    def list_sidechains_for_parent(self, parent_session_id: str) -> list[SidechainSession]:
        sessions = []
        for path in self._base_dir.glob("*.json"):
            try:
                content = path.read_text(encoding="utf-8")
                data = json.loads(content)
                session = SidechainSession.from_dict(data)
                if session.parent_session_id == parent_session_id:
                    sessions.append(session)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue

        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions

    def delete_sidechain(self, session_id: str) -> bool:
        path = self._get_sidechain_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def _get_sidechain_path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self._base_dir / f"{safe_id}.json"

    def _save_session(self, session: SidechainSession, path: Path) -> None:
        data = session.to_dict()
        content = json.dumps(data, indent=2, ensure_ascii=False)
        path.write_text(content, encoding="utf-8")


def record_sidechain_transcript(
    messages: list[dict[str, Any]],
    agent_id: str,
    parent_session_id: str | None = None,
    parent_message_uuid: str | None = None,
    storage: SidechainStorage | None = None,
) -> str:
    if storage is None:
        storage = SidechainStorage()

    return storage.record_sidechain_transcript(
        messages=messages,
        agent_id=agent_id,
        parent_session_id=parent_session_id,
        parent_message_uuid=parent_message_uuid,
    )


def load_sidechain_content(
    session_id: str,
    storage: SidechainStorage | None = None,
) -> list[dict[str, Any]] | None:
    if storage is None:
        storage = SidechainStorage()

    return storage.load_sidechain_content(session_id)


def mark_message_as_sidechain(
    message: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    message["is_sidechain"] = True
    message["agent_id"] = agent_id
    return message


def is_sidechain_message(message: dict[str, Any]) -> bool:
    return message.get("is_sidechain", False)


def filter_sidechain_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [msg for msg in messages if not is_sidechain_message(msg)]


def get_sidechain_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [msg for msg in messages if is_sidechain_message(msg)]
