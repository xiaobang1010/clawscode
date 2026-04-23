from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PREVIEW_SIZE_BYTES = 8 * 1024
PERSISTENCE_THRESHOLD = 100 * 1024
TOOL_RESULTS_SUBDIR = "tool_results"


@dataclass
class PersistedToolResult:
    filepath: str
    original_size: int
    is_json: bool
    preview: str
    has_more: bool


@dataclass
class PersistToolResultError:
    error: str


def get_tool_results_dir(base_dir: Path | None = None) -> Path:
    if base_dir is None:
        base_dir = Path.home() / ".clawscode"
    return base_dir / TOOL_RESULTS_SUBDIR


def ensure_tool_results_dir(base_dir: Path | None = None) -> Path:
    tool_results_dir = get_tool_results_dir(base_dir)
    tool_results_dir.mkdir(parents=True, exist_ok=True)
    return tool_results_dir


def get_tool_result_path(tool_use_id: str, is_json: bool = False, base_dir: Path | None = None) -> Path:
    tool_results_dir = get_tool_results_dir(base_dir)
    ext = ".json" if is_json else ".txt"
    safe_id = tool_use_id.replace("/", "_").replace("\\", "_")
    return tool_results_dir / f"{safe_id}{ext}"


def generate_preview(content: str, preview_size: int = PREVIEW_SIZE_BYTES) -> tuple[str, bool]:
    if len(content) <= preview_size:
        return content, False

    preview = content[:preview_size]
    return preview, True


def persist_tool_result(
    content: str | list[dict[str, Any]],
    tool_use_id: str,
    base_dir: Path | None = None,
) -> PersistedToolResult | PersistToolResultError:
    is_json = isinstance(content, list)

    if is_json:
        has_non_text = any(
            isinstance(block, dict) and block.get("type") != "text"
            for block in content
        )
        if has_non_text:
            return PersistToolResultError(
                error="Cannot persist tool results containing non-text content"
            )

    try:
        ensure_tool_results_dir(base_dir)
    except OSError as e:
        return PersistToolResultError(error=f"Failed to create tool results directory: {e}")

    filepath = get_tool_result_path(tool_use_id, is_json, base_dir)
    content_str = json.dumps(content, indent=2) if is_json else content

    try:
        if not filepath.exists():
            filepath.write_text(content_str, encoding="utf-8")
    except OSError as e:
        return PersistToolResultError(error=f"Failed to write tool result: {e}")

    preview, has_more = generate_preview(content_str, PREVIEW_SIZE_BYTES)

    return PersistedToolResult(
        filepath=str(filepath),
        original_size=len(content_str),
        is_json=is_json,
        preview=preview,
        has_more=has_more,
    )


def load_persisted_tool_result(
    tool_use_id: str,
    base_dir: Path | None = None,
) -> str | list[dict[str, Any]] | None:
    tool_results_dir = get_tool_results_dir(base_dir)

    for ext in [".json", ".txt"]:
        safe_id = tool_use_id.replace("/", "_").replace("\\", "_")
        filepath = tool_results_dir / f"{safe_id}{ext}"

        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8")
                if ext == ".json":
                    return json.loads(content)
                return content
            except (OSError, json.JSONDecodeError):
                return None

    return None


def delete_persisted_tool_result(
    tool_use_id: str,
    base_dir: Path | None = None,
) -> bool:
    tool_results_dir = get_tool_results_dir(base_dir)
    deleted = False

    for ext in [".json", ".txt"]:
        safe_id = tool_use_id.replace("/", "_").replace("\\", "_")
        filepath = tool_results_dir / f"{safe_id}{ext}"

        if filepath.exists():
            try:
                filepath.unlink()
                deleted = True
            except OSError:
                pass

    return deleted


def cleanup_tool_results(base_dir: Path | None = None, max_age_days: int = 7) -> int:
    import time

    tool_results_dir = get_tool_results_dir(base_dir)
    if not tool_results_dir.exists():
        return 0

    deleted_count = 0
    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 60 * 60

    for filepath in tool_results_dir.glob("*"):
        if filepath.is_file():
            try:
                file_mtime = filepath.stat().st_mtime
                if current_time - file_mtime > max_age_seconds:
                    filepath.unlink()
                    deleted_count += 1
            except OSError:
                pass

    return deleted_count


def get_large_output_instructions(raw_output_path: str, content_length: int, format_description: str = "", max_read_length: int = 8000) -> str:
    instructions = "\n\n[读取指令]\n"
    instructions += f"完整输出已保存至: {raw_output_path} (共 {content_length:,} 字节)\n"
    instructions += "你必须使用文件读取工具逐块读取完整内容后再生成摘要或分析。\n"
    instructions += "每次读取后必须明确声明读取进度（如\"已读取 X-Y 行\"）。\n"
    instructions += "如果内容被截断，减小块大小后重新读取。\n"
    instructions += "不要假装已读完所有内容。\n"
    instructions += "不要对未读取的部分进行任何猜测或总结。\n"
    return instructions


def build_large_tool_result_message(result: PersistedToolResult) -> str:
    def format_size(size: int) -> str:
        if size < 1024:
            return f"{size} bytes"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    message = "[PERSISTED OUTPUT]\n"
    message += f"Output too large ({format_size(result.original_size)}). Full output saved to: {result.filepath}\n\n"
    message += f"Preview (first {format_size(PREVIEW_SIZE_BYTES)}):\n"
    message += result.preview
    message += "...\n" if result.has_more else "\n"
    message += get_large_output_instructions(raw_output_path=result.filepath, content_length=result.original_size)
    message += "[END PERSISTED OUTPUT]"

    return message


def maybe_persist_large_tool_result(
    tool_result_block: dict[str, Any],
    tool_name: str,
    threshold: int = PERSISTENCE_THRESHOLD,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    content = tool_result_block.get("content")

    if content is None:
        return tool_result_block

    if isinstance(content, str):
        if len(content) <= threshold:
            return tool_result_block

        tool_use_id = tool_result_block.get("tool_use_id", "")
        result = persist_tool_result(content, tool_use_id, base_dir)

        if isinstance(result, PersistToolResultError):
            return tool_result_block

        return {
            **tool_result_block,
            "content": build_large_tool_result_message(result),
            "persisted_path": result.filepath,
        }

    return tool_result_block


def get_persistence_threshold(tool_name: str, max_result_size_chars: int) -> int:
    if tool_name in _tool_threshold_registry:
        registered = _tool_threshold_registry[tool_name]
        if max_result_size_chars == float("inf"):
            return registered
        return min(max_result_size_chars, registered)

    if max_result_size_chars == float("inf"):
        return PERSISTENCE_THRESHOLD

    return min(max_result_size_chars, PERSISTENCE_THRESHOLD)


_tool_threshold_registry: dict[str, int] = {}


def register_tool_threshold(tool_name: str, max_result_size_chars: int) -> None:
    _tool_threshold_registry[tool_name] = max_result_size_chars


_MIME_TO_EXTENSION: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/json": ".json",
    "text/csv": ".csv",
    "text/html": ".html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}

_BINARY_MIME_PREFIXES = (
    "application/pdf",
    "application/vnd.",
    "audio/",
    "video/",
    "image/",
)


def extension_for_mime_type(mime_type: str) -> str:
    ext = _MIME_TO_EXTENSION.get(mime_type)
    if ext:
        return ext
    if "/" in mime_type:
        subtype = mime_type.split("/")[-1]
        return f".{subtype}"
    return ".bin"


def is_binary_content_type(content_type: str) -> bool:
    if content_type in _MIME_TO_EXTENSION:
        return True
    return content_type.startswith(_BINARY_MIME_PREFIXES)


def persist_binary_content(
    data: bytes,
    mime_type: str,
    persist_id: str,
    base_dir: Path | None = None,
) -> str | None:
    try:
        tool_results_dir = ensure_tool_results_dir(base_dir)
        ext = extension_for_mime_type(mime_type)
        safe_id = persist_id.replace("/", "_").replace("\\", "_")
        filepath = tool_results_dir / f"{safe_id}{ext}"
        filepath.write_bytes(data)
        return str(filepath)
    except OSError:
        return None


def get_binary_blob_saved_message(
    filepath: str,
    mime_type: str,
    size: int,
    source_description: str = "",
) -> str:
    def format_size(s: int) -> str:
        if s < 1024:
            return f"{s} bytes"
        elif s < 1024 * 1024:
            return f"{s / 1024:.1f} KB"
        else:
            return f"{s / (1024 * 1024):.1f} MB"

    message = f"[BINARY CONTENT SAVED]\n"
    message += f"二进制内容已保存至: {filepath}\n"
    message += f"类型: {mime_type} | 大小: {format_size(size)}"
    if source_description:
        message += f" | 来源: {source_description}"
    message += "\n使用文件读取工具查看此文件。"
    return message
