from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def merge_settings(*settings: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for s in settings:
        result.update(s)
    return result
