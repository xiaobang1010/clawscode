from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .message_uuid import generate_uuid, MessageChain


SESSIONS_DIR_NAME = "sessions"
CLAWSCODE_DIR_NAME = ".clawscode"
SESSION_FILE_SUFFIX = ".jsonl"
LEGACY_FILE_SUFFIX = ".json"
MAX_TRANSCRIPT_READ_BYTES = 50 * 1024 * 1024
META_PREFIX = "#META#"
FLUSH_INTERVAL_MS = 100
MAX_CHUNK_BYTES = 100 * 1024 * 1024


def is_transcript_message(entry: dict[str, Any]) -> bool:
    entry_type = entry.get("type", "")
    if entry_type == "progress":
        return False
    return entry_type in ("user", "assistant", "attachment", "system")


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
        self._message_chain = MessageChain()
        if messages:
            self._message_chain.rebuild_chain(messages)
        self.metadata = metadata or {}

    @property
    def messages(self) -> list[dict]:
        return self._message_chain.messages

    @messages.setter
    def messages(self, value: list[dict]) -> None:
        self._message_chain.rebuild_chain(value)

    def add_message(self, message: dict[str, Any]) -> str:
        return self._message_chain.add_message(message)

    def get_message_by_uuid(self, msg_uuid: str) -> dict[str, Any] | None:
        return self._message_chain.get_message_by_uuid(msg_uuid)

    def get_message_chain(self) -> MessageChain:
        return self._message_chain

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
        instance = cls(
            session_id=data.get("session_id"),
            title=data.get("title", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            messages=data.get("messages", []),
            metadata=data.get("metadata", {}),
        )
        return instance


class SessionStorage:
    def __init__(self, home: Path | None = None, storage_path: str = ""):
        if storage_path:
            self._sessions_dir = Path(storage_path)
        else:
            self._home = home or Path.home()
            self._sessions_dir = self._home / CLAWSCODE_DIR_NAME / SESSIONS_DIR_NAME
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._write_queue: list[tuple[Path, str, asyncio.Future | None]] = []
        self._flush_timer: threading.Timer | None = None
        self._drain_lock = threading.Lock()

    def save(self, session: SessionData) -> Path:
        session.updated_at = datetime.now().isoformat()
        path = self._get_session_path(session.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        meta_line = json.dumps({
            "type": "session_meta",
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "metadata": session.metadata,
        }, ensure_ascii=False)
        lines.append(f"{META_PREFIX}{meta_line}")

        for msg in session.messages:
            line = json.dumps(msg, ensure_ascii=False)
            lines.append(line)

        content = "\n".join(lines) + "\n"
        path.write_text(content, encoding="utf-8")

        return path

    def save_incremental(self, session: SessionData, new_messages: list[dict]) -> Path:
        path = self._get_session_path(session.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            return self.save(session)

        for msg in new_messages:
            session.add_message(msg)

        with open(path, "a", encoding="utf-8") as f:
            for msg in new_messages:
                line = json.dumps(msg, ensure_ascii=False)
                f.write(line + "\n")

        session.updated_at = datetime.now().isoformat()
        self.re_append_session_metadata(session)

        return path

    def re_append_session_metadata(self, session: SessionData) -> None:
        path = self._get_session_path(session.session_id)
        if not path.exists():
            return

        meta_line = json.dumps({
            "type": "session_meta",
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "metadata": session.metadata,
        }, ensure_ascii=False)

        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{META_PREFIX}{meta_line}\n")

    def load(self, session_id: str) -> SessionData | None:
        jsonl_path = self._get_session_path(session_id)
        json_path = self._get_legacy_session_path(session_id)

        if jsonl_path.exists():
            return self._load_jsonl(jsonl_path)

        if json_path.exists():
            session = self._load_json(json_path)
            if session is not None:
                self._migrate_json_to_jsonl(json_path, session)
            return session

        return None

    def _load_jsonl(self, path: Path) -> SessionData | None:
        try:
            file_size = path.stat().st_size
            read_limit = min(file_size, MAX_TRANSCRIPT_READ_BYTES)

            with open(path, "rb") as f:
                if file_size > MAX_TRANSCRIPT_READ_BYTES:
                    f.seek(file_size - MAX_TRANSCRIPT_READ_BYTES)
                    f.readline()

                raw = f.read(read_limit)

            content = raw.decode("utf-8", errors="replace")
        except OSError:
            return None

        messages: list[dict[str, Any]] = []
        meta: dict[str, Any] = {}
        latest_meta: dict[str, Any] = {}

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith(META_PREFIX):
                try:
                    meta_data = json.loads(line[len(META_PREFIX):])
                    latest_meta = meta_data
                except json.JSONDecodeError:
                    continue
                continue

            try:
                entry = json.loads(line)
                if isinstance(entry, dict) and is_transcript_message(entry):
                    messages.append(entry)
                elif isinstance(entry, dict) and entry.get("role") in ("system", "user", "assistant", "tool"):
                    entry_type = entry.get("role")
                    if entry_type == "system":
                        entry["type"] = "system"
                    elif entry_type == "user":
                        entry["type"] = "user"
                    elif entry_type == "assistant":
                        entry["type"] = "assistant"
                    messages.append(entry)
            except json.JSONDecodeError:
                continue

        session_id = latest_meta.get("session_id", path.stem)
        title = latest_meta.get("title", "")
        created_at = latest_meta.get("created_at", "")
        updated_at = latest_meta.get("updated_at", "")
        metadata = latest_meta.get("metadata", {})

        return SessionData(
            session_id=session_id,
            title=title,
            created_at=created_at,
            updated_at=updated_at,
            messages=messages,
            metadata=metadata,
        )

    def _load_json(self, path: Path) -> SessionData | None:
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return SessionData.from_dict(data)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None

    def _migrate_json_to_jsonl(self, json_path: Path, session: SessionData) -> None:
        jsonl_path = self._get_session_path(session.session_id)
        try:
            self.save(session)
            json_path.rename(json_path.with_suffix(".json.bak"))
        except OSError:
            pass

    def list_sessions(self) -> list[SessionData]:
        sessions: list[SessionData] = []

        for path in sorted(self._sessions_dir.glob(f"*{SESSION_FILE_SUFFIX}")):
            try:
                session = self._load_jsonl(path)
                if session:
                    sessions.append(session)
            except Exception:
                continue

        for path in sorted(self._sessions_dir.glob(f"*{LEGACY_FILE_SUFFIX}")):
            if path.suffix == ".bak":
                continue
            try:
                session = self._load_json(path)
                if session:
                    sessions.append(session)
            except Exception:
                continue

        seen_ids: set[str] = set()
        unique_sessions: list[SessionData] = []
        for s in sessions:
            if s.session_id not in seen_ids:
                seen_ids.add(s.session_id)
                unique_sessions.append(s)

        unique_sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return unique_sessions

    def delete(self, session_id: str) -> bool:
        deleted = False
        for suffix in (SESSION_FILE_SUFFIX, LEGACY_FILE_SUFFIX, ".json.bak"):
            path = self._sessions_dir / f"{session_id.replace('/', '_').replace('\\', '_')}{suffix}"
            if path.exists():
                try:
                    path.unlink()
                    deleted = True
                except OSError:
                    pass
        return deleted

    def get_session_path(self, session_id: str) -> Path:
        return self._get_session_path(session_id)

    def _get_session_path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self._sessions_dir / f"{safe_id}{SESSION_FILE_SUFFIX}"

    def _get_legacy_session_path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self._sessions_dir / f"{safe_id}{LEGACY_FILE_SUFFIX}"

    def enqueue_write(self, path: Path, line: str) -> None:
        with self._drain_lock:
            self._write_queue.append((path, line, None))
            self._schedule_drain()

    def _schedule_drain(self) -> None:
        if self._flush_timer is not None:
            return
        self._flush_timer = threading.Timer(FLUSH_INTERVAL_MS / 1000.0, self._drain_write_queue)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _drain_write_queue(self) -> None:
        with self._drain_lock:
            self._flush_timer = None
            batch = self._write_queue[:]
            self._write_queue.clear()

        if not batch:
            return

        file_batches: dict[Path, list[str]] = {}
        for path, line, _ in batch:
            file_batches.setdefault(path, []).append(line)

        for path, lines in file_batches.items():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                content = ""
                for line in lines:
                    if len(content) + len(line) + 1 >= MAX_CHUNK_BYTES:
                        with open(path, "a", encoding="utf-8") as f:
                            f.write(content)
                        content = ""
                    content += line + "\n"
                if content:
                    with open(path, "a", encoding="utf-8") as f:
                        f.write(content)
            except OSError:
                pass

        if self._write_queue:
            self._schedule_drain()

    def flush(self) -> None:
        with self._drain_lock:
            if self._flush_timer is not None:
                self._flush_timer.cancel()
                self._flush_timer = None
        self._drain_write_queue()


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
