from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
MAX_RESULT_SIZE = 100000

_file_cache: dict[str, tuple[float, str]] = {}


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

        cached = _file_cache.get(str(path.resolve()))
        if cached:
            mtime, content = cached
            if path.stat().st_mtime == mtime:
                lines = content.splitlines()
                start = (input.offset or 1) - 1
                end = start + (input.limit or len(lines))
                selected = lines[start:end]
                numbered = [f"{i + 1:6}\u2192{line}" for i, line in enumerate(selected, start=start + 1)]
                return ToolResult(output="\n".join(numbered))

        return self._read_text(path, input)

    def _read_text(self, path: Path, input: FileReadInput) -> ToolResult:
        content = path.read_text(encoding="utf-8", errors="replace")
        _file_cache[str(path.resolve())] = (path.stat().st_mtime, content)

        lines = content.splitlines()
        start = (input.offset or 1) - 1
        end = start + (input.limit or len(lines))
        selected = lines[start:end]
        numbered = [f"{i + 1:6}\u2192{line}" for i, line in enumerate(selected, start=start + 1)]

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
