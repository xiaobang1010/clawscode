from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.services.file_state_cache import FileState, FileStateCache
from src.tool import Tool, ToolResult

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
MAX_RESULT_SIZE = 100000


class FileReadInput(BaseModel):
    file_path: str = Field(description="文件路径")
    offset: int | None = Field(default=None, description="起始行号")
    limit: int | None = Field(default=None, description="读取行数")


class FileReadTool(Tool):
    name = "FileRead"
    description = "读取文件内容。支持文本文件按行读取和图片文件 Base64 编码。"
    input_schema = FileReadInput
    is_readonly = True

    async def call(self, input: FileReadInput, context: Any) -> ToolResult:
        path = Path(input.file_path)
        if not path.exists():
            return ToolResult(output=f"文件不存在: {input.file_path}", is_error=True)
        if not path.is_file():
            return ToolResult(output=f"不是文件: {input.file_path}", is_error=True)

        read_files = getattr(context, "read_files", None)
        if read_files is not None:
            read_files.add(str(path.resolve()))

        if path.suffix.lower() in IMAGE_EXTENSIONS:
            return self._read_image(path)

        file_cache = self._get_file_cache(context)
        return self._read_text(path, input, file_cache)

    def _get_file_cache(self, context: Any) -> FileStateCache:
        file_cache = getattr(context, "read_file_state", None)
        if file_cache is None:
            file_cache = FileStateCache()
        return file_cache

    def _read_text(self, path: Path, input: FileReadInput, file_cache: FileStateCache) -> ToolResult:
        resolved_path = str(path.resolve())
        current_mtime = path.stat().st_mtime

        cached_state = file_cache.get(resolved_path)
        is_partial = input.offset is not None or input.limit is not None

        if cached_state and cached_state.timestamp == current_mtime:
            if not is_partial and not cached_state.is_partial_view:
                lines = cached_state.content.splitlines()
                numbered = [f"{i + 1:6}\u2192{line}" for i, line in enumerate(lines, start=1)]
                result = "\n".join(numbered)
                if len(result) > MAX_RESULT_SIZE:
                    result = result[:MAX_RESULT_SIZE] + f"\n...[截断，文件过大]"
                return ToolResult(output=result)

            if cached_state.is_partial_view and is_partial:
                lines = cached_state.content.splitlines()
                start = (input.offset or 1) - 1
                end = start + (input.limit or len(lines))
                selected = lines[start:end]
                numbered = [f"{i + 1:6}\u2192{line}" for i, line in enumerate(selected, start=start + 1)]
                return ToolResult(output="\n".join(numbered))

        content = path.read_text(encoding="utf-8", errors="replace")

        if is_partial:
            lines = content.splitlines()
            start = (input.offset or 1) - 1
            end = start + (input.limit or len(lines))
            selected = lines[start:end]

            partial_content = "\n".join(selected)
            file_cache.set(resolved_path, FileState(
                content=partial_content,
                timestamp=current_mtime,
                offset=input.offset,
                limit=input.limit,
                is_partial_view=True,
            ))

            numbered = [f"{i + 1:6}\u2192{line}" for i, line in enumerate(selected, start=start + 1)]
            result = "\n".join(numbered)
            if len(result) > MAX_RESULT_SIZE:
                result = result[:MAX_RESULT_SIZE] + f"\n...[截断，文件过大]"
            return ToolResult(output=result)

        file_cache.set(resolved_path, FileState(
            content=content,
            timestamp=current_mtime,
            offset=None,
            limit=None,
            is_partial_view=False,
        ))

        lines = content.splitlines()
        numbered = [f"{i + 1:6}\u2192{line}" for i, line in enumerate(lines, start=1)]
        result = "\n".join(numbered)
        if len(result) > MAX_RESULT_SIZE:
            result = result[:MAX_RESULT_SIZE] + f"\n...[截断，文件过大]"

        return ToolResult(output=result)

    def _read_image(self, path: Path) -> ToolResult:
        try:
            data = path.read_bytes()
            encoded = base64.b64encode(data).decode("ascii")
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
            }
            mime = mime_map.get(path.suffix.lower(), "application/octet-stream")
            return ToolResult(output=f"[图片: {path.name} ({mime}, {len(data)} bytes)]\ndata:{mime};base64,{encoded[:200]}...")
        except Exception as e:
            return ToolResult(output=f"读取图片失败: {e}", is_error=True)
