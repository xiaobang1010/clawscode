from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MessageStats:
    total: int = 0
    by_role: dict[str, int] = field(default_factory=dict)
    tool_calls: int = 0
    tool_results: int = 0
    total_chars: int = 0


class MessagePipeline:
    def standardize(self, messages: list[dict]) -> list[dict]:
        result = []
        for msg in messages:
            standardized = self._standardize_message(msg)
            if standardized is not None:
                result.append(standardized)
        return result

    def _standardize_message(self, msg: dict) -> dict | None:
        if not isinstance(msg, dict):
            return None

        role = msg.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            return None

        result: dict[str, Any] = {"role": role}

        content = msg.get("content")
        if content is not None:
            result["content"] = self._standardize_content(content)
        else:
            result["content"] = None

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id:
                result["tool_call_id"] = tool_call_id

        if role == "assistant" and "tool_calls" in msg:
            result["tool_calls"] = msg["tool_calls"]

        return result

    def _standardize_content(self, content: Any) -> Any:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            result = []
            for block in content:
                if isinstance(block, str):
                    result.append({"type": "text", "text": block})
                elif isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type == "text":
                        result.append({"type": "text", "text": block.get("text", "")})
                    elif block_type == "image_url":
                        result.append(block)
                    elif block_type == "tool_use":
                        result.append(block)
                    elif block_type == "tool_result":
                        result.append(block)
                    else:
                        result.append(block)
            return result

        return str(content)

    def count_messages(self, messages: list[dict]) -> MessageStats:
        stats = MessageStats()
        for msg in messages:
            stats.total += 1
            role = msg.get("role", "unknown")
            stats.by_role[role] = stats.by_role.get(role, 0) + 1

            if role == "assistant" and msg.get("tool_calls"):
                stats.tool_calls += len(msg["tool_calls"])

            if role == "tool":
                stats.tool_results += 1

            text = self._extract_text(msg)
            if text:
                stats.total_chars += len(text)

        return stats

    def deduplicate(self, messages: list[dict]) -> list[dict]:
        if not messages:
            return messages

        result = [messages[0]]
        for i in range(1, len(messages)):
            prev = messages[i - 1]
            curr = messages[i]

            if self._is_duplicate(prev, curr):
                continue

            result.append(curr)

        return result

    def _is_duplicate(self, msg_a: dict, msg_b: dict) -> bool:
        if msg_a.get("role") != msg_b.get("role"):
            return False

        content_a = self._extract_text(msg_a)
        content_b = self._extract_text(msg_b)

        if content_a is None or content_b is None:
            return False

        return content_a == content_b

    def process_content_array(self, messages: list[dict]) -> list[dict]:
        result = []
        for msg in messages:
            processed = dict(msg)
            content = msg.get("content")

            if isinstance(content, list):
                processed["content"] = self._merge_text_blocks(content)

            result.append(processed)

        return result

    def _merge_text_blocks(self, blocks: list[dict | str]) -> list[dict | str]:
        if not blocks:
            return blocks

        merged = []
        text_buffer = []

        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_buffer.append(block.get("text", ""))
            else:
                if text_buffer:
                    merged.append({"type": "text", "text": "\n".join(text_buffer)})
                    text_buffer = []
                merged.append(block)

        if text_buffer:
            merged.append({"type": "text", "text": "\n".join(text_buffer)})

        return merged

    def link_read_edit_context(self, messages: list[dict]) -> list[dict]:
        result = []
        read_files: dict[str, dict] = {}

        for msg in messages:
            processed = dict(msg)

            role = msg.get("role")
            if role == "tool":
                tool_name = self._get_tool_name_for_result(messages, msg)
                content = self._extract_text(msg)

                if tool_name == "FileRead" and content:
                    file_path = self._extract_file_path(msg) or self._extract_file_path_from_content(content)
                    if file_path:
                        read_files[file_path] = {
                            "message": msg,
                            "content_preview": content[:500],
                        }

                if tool_name == "FileEdit" and content:
                    file_path = self._extract_file_path(msg) or self._extract_file_path_from_content(content)
                    if file_path and file_path in read_files:
                        processed["_linked_read"] = read_files[file_path]

            result.append(processed)

        return result

    def _get_tool_name_for_result(self, messages: list[dict], tool_msg: dict) -> str | None:
        tool_call_id = tool_msg.get("tool_call_id")
        if not tool_call_id:
            return None

        for msg in messages:
            tool_calls = msg.get("tool_calls", [])
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = tc.get("id")
                        if tc_id == tool_call_id:
                            func = tc.get("function", {})
                            if isinstance(func, dict):
                                return func.get("name")
        return None

    def _extract_file_path(self, msg: dict) -> str | None:
        content = msg.get("content")
        if isinstance(content, str):
            return self._extract_file_path_from_content(content)
        return None

    def _extract_file_path_from_content(self, content: str) -> str | None:
        for prefix in ("文件：", "文件路径：", "path: ", "file: "):
            idx = content.find(prefix)
            if idx >= 0:
                line = content[idx + len(prefix):].split("\n")[0].strip()
                if line:
                    return line
        return None

    def _extract_text(self, message: dict) -> str | None:
        content = message.get("content")
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts) if parts else None
        return str(content)
