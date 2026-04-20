from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


MAX_SNAPSHOTS = 50
HISTORY_DIR_NAME = "file_history"
CLAWSCODE_DIR_NAME = ".clawscode"


@dataclass
class FileSnapshot:
    path: str
    content: str
    timestamp: str
    snapshot_id: str


class FileHistory:
    def __init__(self, cwd: Path, max_snapshots: int = MAX_SNAPSHOTS):
        self._cwd = cwd
        self._max_snapshots = max_snapshots
        self._history_dir = cwd / CLAWSCODE_DIR_NAME / HISTORY_DIR_NAME
        self._snapshots: list[FileSnapshot] = []

    def create_snapshot(self, file_path: str | Path) -> FileSnapshot | None:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return None

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        timestamp = datetime.now().isoformat()
        snapshot_id = f"{len(self._snapshots):04d}"

        snapshot = FileSnapshot(
            path=str(path),
            content=content,
            timestamp=timestamp,
            snapshot_id=snapshot_id,
        )

        self._snapshots.append(snapshot)
        self._save_snapshot_to_disk(snapshot)
        self._cleanup_old_snapshots()

        return snapshot

    def create_batch_snapshot(self, file_paths: list[str | Path]) -> list[FileSnapshot]:
        results = []
        for fp in file_paths:
            snapshot = self.create_snapshot(fp)
            if snapshot is not None:
                results.append(snapshot)
        return results

    def restore_snapshot(self, snapshot_id: str) -> bool:
        snapshot = self._find_snapshot(snapshot_id)
        if snapshot is None:
            return False

        try:
            path = Path(snapshot.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(snapshot.content, encoding="utf-8")
            return True
        except OSError:
            return False

    def get_snapshots(self) -> list[FileSnapshot]:
        return list(self._snapshots)

    def get_snapshots_for_file(self, file_path: str | Path) -> list[FileSnapshot]:
        resolved = str(Path(file_path).resolve())
        return [s for s in self._snapshots if Path(s.path).resolve() == Path(resolved).resolve()]

    def _find_snapshot(self, snapshot_id: str) -> FileSnapshot | None:
        for s in self._snapshots:
            if s.snapshot_id == snapshot_id:
                return s
        return None

    def _save_snapshot_to_disk(self, snapshot: FileSnapshot) -> None:
        try:
            snap_dir = self._history_dir / snapshot.snapshot_id
            snap_dir.mkdir(parents=True, exist_ok=True)

            rel_path = self._get_relative_path(snapshot.path)
            file_path = snap_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(snapshot.content, encoding="utf-8")

            meta_path = snap_dir / "_meta.txt"
            meta_path.write_text(
                f"path: {snapshot.path}\ntimestamp: {snapshot.timestamp}\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def _cleanup_old_snapshots(self) -> None:
        while len(self._snapshots) > self._max_snapshots:
            old = self._snapshots.pop(0)
            self._remove_snapshot_from_disk(old)

    def _remove_snapshot_from_disk(self, snapshot: FileSnapshot) -> None:
        try:
            snap_dir = self._history_dir / snapshot.snapshot_id
            if snap_dir.exists():
                shutil.rmtree(snap_dir, ignore_errors=True)
        except OSError:
            pass

    def _get_relative_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).relative_to(self._cwd))
        except ValueError:
            return Path(file_path).name
