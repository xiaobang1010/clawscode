from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.services.file_state_cache import FileState, FileStateCache, create_file_state_cache
from src.services.session_storage import SessionData, SessionStorage


FILE_UNCHANGED_STUB = "File unchanged since last read. The content from the earlier Read tool_result in this conversation is still current — refer to that instead of re-reading."
ASK_READ_FILE_STATE_CACHE_SIZE = 10
LINE_NUMBER_PREFIX_RE = re.compile(r"^\s*\d+→")


def _strip_line_number_prefix(line: str) -> str:
    return LINE_NUMBER_PREFIX_RE.sub("", line)


def _expand_path(file_path: str, cwd: str) -> str:
    if os.path.isabs(file_path):
        return os.path.normpath(file_path)
    return os.path.normpath(os.path.join(cwd, file_path))


def _get_file_modification_time(file_path: str) -> float:
    try:
        return os.path.getmtime(file_path)
    except OSError:
        return 0.0


def _read_file_with_metadata(file_path: str) -> tuple[str, float] | None:
    try:
        mtime = _get_file_modification_time(file_path)
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content, mtime
    except OSError:
        return None


def extract_read_files_from_messages(
    messages: list[dict],
    cwd: str = "",
    max_size: int = ASK_READ_FILE_STATE_CACHE_SIZE,
) -> FileStateCache:
    cache = create_file_state_cache(max_entries=max_size)

    file_read_tool_use_ids: dict[str, str] = {}
    file_write_tool_use_ids: dict[str, tuple[str, str]] = {}
    file_edit_tool_use_ids: dict[str, str] = {}

    for msg in messages:
        role = msg.get("role", "")
        if role != "assistant":
            continue
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function", {})
            name = fn.get("name", "")
            tc_id = tc.get("id", "")
            if not tc_id:
                continue

            args_str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except (json.JSONDecodeError, TypeError):
                continue

            if name in ("Read", "FileRead"):
                fp = args.get("file_path") or args.get("path", "")
                offset = args.get("offset")
                limit = args.get("limit")
                if fp and offset is None and limit is None:
                    absolute_path = _expand_path(fp, cwd)
                    file_read_tool_use_ids[tc_id] = absolute_path

            elif name in ("Write", "FileWrite"):
                fp = args.get("file_path") or args.get("path", "")
                content = args.get("content", "")
                if fp:
                    absolute_path = _expand_path(fp, cwd)
                    file_write_tool_use_ids[tc_id] = (absolute_path, content)

            elif name in ("Edit", "FileEdit"):
                fp = args.get("file_path") or args.get("path", "")
                if fp:
                    absolute_path = _expand_path(fp, cwd)
                    file_edit_tool_use_ids[tc_id] = absolute_path

    for msg in messages:
        role = msg.get("role", "")
        if role != "tool" and role != "user":
            continue

        content = msg.get("content", "")
        if role == "user":
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                tool_use_id = block.get("tool_use_id", "")
                if not tool_use_id:
                    continue
                _process_tool_result_block(
                    block, tool_use_id,
                    file_read_tool_use_ids,
                    file_write_tool_use_ids,
                    file_edit_tool_use_ids,
                    cache,
                )
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            if not tool_call_id:
                continue
            block = {
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": content,
                "is_error": msg.get("is_error", False),
            }
            _process_tool_result_block(
                block, tool_call_id,
                file_read_tool_use_ids,
                file_write_tool_use_ids,
                file_edit_tool_use_ids,
                cache,
            )

    return cache


def _process_tool_result_block(
    block: dict,
    tool_use_id: str,
    file_read_ids: dict[str, str],
    file_write_ids: dict[str, tuple[str, str]],
    file_edit_ids: dict[str, str],
    cache: FileStateCache,
) -> None:
    is_error = block.get("is_error", False)
    result_content = block.get("content", "")

    if tool_use_id in file_read_ids:
        file_path = file_read_ids[tool_use_id]
        if isinstance(result_content, str):
            if result_content.startswith(FILE_UNCHANGED_STUB):
                return
            processed = result_content
            if "\n" in processed:
                lines = processed.split("\n")
                stripped = "\n".join(_strip_line_number_prefix(l) for l in lines)
                processed = stripped.strip()
            timestamp = _get_file_modification_time(file_path)
            cache.set(file_path, FileState(
                content=processed,
                timestamp=timestamp if timestamp > 0 else 0.0,
                offset=None,
                limit=None,
            ))

    if tool_use_id in file_write_ids:
        file_path, write_content = file_write_ids[tool_use_id]
        if not is_error:
            timestamp = _get_file_modification_time(file_path)
            cache.set(file_path, FileState(
                content=write_content,
                timestamp=timestamp if timestamp > 0 else 0.0,
                offset=None,
                limit=None,
            ))

    if tool_use_id in file_edit_ids:
        file_path = file_edit_ids[tool_use_id]
        if not is_error:
            result = _read_file_with_metadata(file_path)
            if result:
                disk_content, mtime = result
                cache.set(file_path, FileState(
                    content=disk_content,
                    timestamp=mtime,
                    offset=None,
                    limit=None,
                ))


def record_content_replacement(
    records: list[dict[str, Any]],
    session_id: str,
    storage: SessionStorage | None = None,
) -> None:
    if not records:
        return

    _storage = storage or SessionStorage()
    session = _storage.load(session_id)
    if session is None:
        return

    existing = session.metadata.get("content_replacements", [])
    if not isinstance(existing, list):
        existing = []

    for record in records:
        existing.append({
            "kind": record.get("kind", "tool-result"),
            "tool_use_id": record.get("tool_use_id", ""),
            "replacement": record.get("replacement", ""),
        })

    session.metadata["content_replacements"] = existing
    _storage.save(session)


@dataclass
class RestoredSession:
    session_data: SessionData
    messages: list[dict]
    metadata: dict[str, Any]
    file_history: list[str] = field(default_factory=list)
    todo_list: list[dict] = field(default_factory=list)
    agent_type: str = ""
    model_override: str = ""
    file_state_cache: FileStateCache | None = None


class SessionRestore:
    def __init__(self, storage: SessionStorage | None = None, home: Path | None = None):
        self._storage = storage or SessionStorage(home=home)

    def restore(self, session_id: str, cwd: str = "") -> RestoredSession | None:
        session = self._storage.load(session_id)
        if session is None:
            return None

        messages = self._rebuild_messages(session)
        metadata = self._rebuild_metadata(session)
        file_history = self._restore_file_history(session)
        todo_list = self._restore_todo_list(session)
        agent_type, model_override = self._restore_agent_config(session)

        file_state_cache = extract_read_files_from_messages(messages, cwd=cwd)

        return RestoredSession(
            session_data=session,
            messages=messages,
            metadata=metadata,
            file_history=file_history,
            todo_list=todo_list,
            agent_type=agent_type,
            model_override=model_override,
            file_state_cache=file_state_cache,
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
