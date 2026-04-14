from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.state import SessionState


CLAWSCODE_DIR_NAME = ".clawscode"
STATE_FILE_NAME = "session_state.json"


class SessionStateManager:
    def __init__(self, cwd: Path):
        self._cwd = cwd
        self._state = SessionState.IDLE
        self._listeners: list[Callable[[SessionState, SessionState], None]] = []
        self._state_file = cwd / CLAWSCODE_DIR_NAME / STATE_FILE_NAME

    @property
    def state(self) -> SessionState:
        return self._state

    def transition_to(self, new_state: SessionState) -> None:
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        self._write_external_metadata()
        self._notify_listeners(old_state, new_state)

    def add_listener(self, listener: Callable[[SessionState, SessionState], None]) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[SessionState, SessionState], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def write_external_metadata(self, extra: dict | None = None) -> None:
        self._write_external_metadata(extra)

    def _write_external_metadata(self, extra: dict | None = None) -> None:
        data = {
            "state": self._state.value,
            "updated_at": datetime.now().isoformat(),
        }
        if extra:
            data.update(extra)

        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    def _notify_listeners(self, old_state: SessionState, new_state: SessionState) -> None:
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception:
                pass
