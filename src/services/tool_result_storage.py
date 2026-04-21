from __future__ import annotations

import os
import tempfile
from pathlib import Path


class ToolResultStorage:
    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or Path(tempfile.gettempdir()) / "clawscode" / "tool_results"

    def _ensure_dir(self) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, tool_name: str, content: str, max_chars: int = 25000) -> tuple[str, str]:
        if len(content) <= max_chars:
            return content, ""

        self._ensure_dir()
        import hashlib
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
        filename = f"{tool_name}_{content_hash}.txt"
        filepath = self._base_dir / filename

        try:
            filepath.write_text(content, encoding="utf-8")
        except OSError:
            return content, ""

        preview_chars = max_chars // 2
        preview = content[:preview_chars]
        truncated_msg = (
            f"\n\n...[工具结果过大，已截断。完整结果已保存到: {filepath}]..."
        )
        return preview + truncated_msg, str(filepath)

    def read(self, filepath: str) -> str | None:
        try:
            path = Path(filepath)
            if path.exists():
                return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
        return None


def apply_tool_result_budget(
    messages: list[dict],
    max_result_chars: int = 25000,
    storage: ToolResultStorage | None = None,
) -> list[dict]:
    if storage is None:
        storage = ToolResultStorage()

    result = []
    for msg in messages:
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if len(content) > max_result_chars:
                new_content, filepath = storage.store(
                    msg.get("tool_call_id", "unknown"),
                    content,
                    max_result_chars,
                )
                new_msg = dict(msg)
                new_msg["content"] = new_content
                result.append(new_msg)
            else:
                result.append(msg)
        else:
            result.append(msg)

    return result
