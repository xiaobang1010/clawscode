from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from src.services.tool_result_persistence import (
    extension_for_mime_type,
    is_binary_content_type,
    persist_binary_content,
    get_binary_blob_saved_message,
    get_large_output_instructions,
)


def get_large_output_instructions_mcp(
    result_type: str,
    content_length: int,
    format_description: str = "",
) -> str:
    return get_large_output_instructions(
        raw_output_path="",
        content_length=content_length,
        format_description=format_description or get_format_description(result_type),
    )


def persist_mcp_binary_content(
    data: bytes,
    mime_type: str,
    tool_name: str,
    base_dir: Path | None = None,
) -> str | None:
    content_hash = hashlib.sha256(data).hexdigest()[:12]
    persist_id = f"mcp_{tool_name}_{content_hash}"
    result = persist_binary_content(data, mime_type, persist_id, base_dir)
    if result:
        return result
    return None


def get_format_description(result_type: str, schema: dict[str, Any] | None = None) -> str:
    type_descriptions: dict[str, str] = {
        "json": "JSON 结构化数据",
        "csv": "CSV 表格数据",
        "html": "HTML 文档",
        "text": "纯文本",
        "image": "图片内容",
        "table": "表格数据",
        "list": "列表数据",
        "error": "错误信息",
    }
    desc = type_descriptions.get(result_type, result_type)

    if schema:
        if isinstance(schema, dict):
            fields = list(schema.keys())[:5]
            if fields:
                desc += f" (字段: {', '.join(fields)})"
    return desc


def build_mcp_persisted_message(
    persisted_path: str,
    mime_type: str,
    size: int,
    result_type: str = "",
    schema: dict[str, Any] | None = None,
) -> str:
    if is_binary_content_type(mime_type):
        return get_binary_blob_saved_message(
            filepath=persisted_path,
            mime_type=mime_type,
            size=size,
            source_description=f"MCP 工具输出 ({result_type})",
        )

    format_desc = get_format_description(result_type, schema)
    message = f"[MCP PERSISTED OUTPUT]\n"
    message += f"MCP 工具输出过大 ({size:,} 字节). 完整输出已保存至: {persisted_path}\n"
    message += f"格式: {format_desc}\n"
    message += get_large_output_instructions_mcp(result_type, size, format_desc)
    message += "[END MCP PERSISTED OUTPUT]"
    return message
