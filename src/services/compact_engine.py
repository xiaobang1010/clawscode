from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from src.services.token_counter import count_tokens

AUTOCOMPACT_BUFFER_TOKENS = 13000
WARNING_THRESHOLD_TOKENS = 20000
MAX_CONSECUTIVE_FAILURES = 3
MIN_RECENT_MESSAGES = 10

BASE_COMPACT_PROMPT = """请将以下对话历史压缩为一份结构化摘要。摘要必须包含以下 9 个部分，每部分用明确的标题标记：

1. **请求意图**：用户的核心需求和目标
2. **技术概念**：涉及的技术栈、框架、库、关键概念
3. **文件和代码**：读取、创建或修改的文件，及其关键变更
4. **错误修复**：遇到的问题和解决方案
5. **问题解决**：重要的决策、讨论和推理过程
6. **用户消息**：用户的所有重要消息摘要
7. **待办任务**：当前任务列表状态
8. **当前工作**：最近正在进行的工作内容
9. **下一步**：接下来需要执行的操作

请确保摘要信息完整，不丢失任何关键上下文。以 Markdown 格式输出。"""

PARTIAL_COMPACT_PROMPT = """请将以下最近的对话消息压缩为一份简洁摘要。保留关键信息，包括：
- 用户请求
- 工具调用和结果
- 重要决策和结论
- 当前工作状态

以 Markdown 格式输出摘要。"""

NO_TOOLS_PREAMBLE = "重要：请不要调用任何工具，仅根据提供的对话内容生成摘要。"

COMPACT_BOUNDARY_PREFIX = "[compact]"


@dataclass
class CompactResult:
    summary: str
    original_token_count: int
    compacted_token_count: int
    messages_removed: int
    is_full: bool


_consecutive_failures = 0


def build_compact_messages(messages: list[dict], custom_instructions: str = "") -> list[dict]:
    non_system = [m for m in messages if m.get("role") != "system"]
    if not non_system:
        return []

    content_parts = ["<conversation>\n"]
    for msg in non_system:
        role = msg.get("role", "unknown")
        text = _extract_text(msg)
        if text:
            content_parts.append(f"[{role}]: {text}\n")
    content_parts.append("</conversation>")

    prompt = BASE_COMPACT_PROMPT
    if custom_instructions:
        prompt += f"\n\n额外压缩指令：{custom_instructions}"

    return [
        {
            "role": "system",
            "content": NO_TOOLS_PREAMBLE,
        },
        {
            "role": "user",
            "content": prompt + "\n\n" + "".join(content_parts),
        },
    ]


def build_partial_compact_messages(
    messages: list[dict],
    recent_count: int = 5,
) -> list[dict]:
    non_system = [m for m in messages if m.get("role") != "system"]
    if not non_system:
        return []

    recent = non_system[-recent_count:]
    content_parts = ["<recent_messages>\n"]
    for msg in recent:
        role = msg.get("role", "unknown")
        text = _extract_text(msg)
        if text:
            content_parts.append(f"[{role}]: {text}\n")
    content_parts.append("</recent_messages>")

    return [
        {
            "role": "system",
            "content": NO_TOOLS_PREAMBLE,
        },
        {
            "role": "user",
            "content": PARTIAL_COMPACT_PROMPT + "\n\n" + "".join(content_parts),
        },
    ]


def create_compact_boundary_message(summary: str, original_count: int, compacted_count: int) -> dict:
    return {
        "role": "user",
        "content": (
            f"{COMPACT_BOUNDARY_PREFIX} 上下文压缩完成。\n"
            f"原始消息约 {original_count} tokens，压缩后约 {compacted_count} tokens。\n"
            f"摘要：\n{summary}"
        ),
    }


def is_compact_boundary(message: dict) -> bool:
    content = _extract_text(message)
    return content is not None and content.startswith(COMPACT_BOUNDARY_PREFIX)


def apply_compaction(
    messages: list[dict],
    summary: str,
    keep_recent: int = MIN_RECENT_MESSAGES,
) -> list[dict]:
    global _consecutive_failures

    system = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    original_count = len(non_system)

    boundary = create_compact_boundary_message(
        summary,
        count_tokens(non_system),
        count_tokens([{"role": "user", "content": summary}]),
    )

    if len(non_system) <= keep_recent:
        kept = non_system
    else:
        kept = non_system[-keep_recent:]

    result = system + [boundary] + kept
    _consecutive_failures = 0

    return result


async def compact_with_llm(
    messages: list[dict],
    max_tokens: int,
    create_stream_fn: Any = None,
    custom_instructions: str = "",
    partial: bool = False,
) -> list[dict]:
    global _consecutive_failures

    used = count_tokens(messages)
    buffer = max_tokens - used

    if buffer >= WARNING_THRESHOLD_TOKENS:
        return messages

    if _consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return compact_if_needed(messages, max_tokens)

    if create_stream_fn is None:
        return compact_if_needed(messages, max_tokens)

    try:
        if partial:
            compact_msgs = build_partial_compact_messages(messages)
        else:
            compact_msgs = build_compact_messages(messages, custom_instructions)

        if not compact_msgs:
            return messages

        summary_text = ""
        async for event in create_stream_fn(
            compact_msgs,
            [],
            "请根据对话内容生成压缩摘要。不要调用任何工具。",
        ):
            if event.type == "text_delta":
                summary_text += event.data.get("text", "")

        if not summary_text.strip():
            _consecutive_failures += 1
            return compact_if_needed(messages, max_tokens)

        result = apply_compaction(messages, summary_text)
        _consecutive_failures = 0
        return result

    except Exception:
        _consecutive_failures += 1
        return compact_if_needed(messages, max_tokens)


def compact_if_needed(messages: list[dict], max_tokens: int) -> list[dict]:
    global _consecutive_failures

    used = count_tokens(messages)
    buffer = max_tokens - used

    if buffer >= WARNING_THRESHOLD_TOKENS:
        return messages

    if _consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return messages

    try:
        system = [m for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]

        target_tokens = max_tokens - AUTOCOMPACT_BUFFER_TOKENS
        recent_count = len(non_system)
        for n in range(MIN_RECENT_MESSAGES, len(non_system) + 1):
            candidate = system + non_system[-n:]
            if count_tokens(candidate) <= target_tokens:
                recent_count = n
                break
        else:
            recent_count = MIN_RECENT_MESSAGES

        compacted = system + non_system[-recent_count:]
        _consecutive_failures = 0
        return compacted
    except Exception:
        _consecutive_failures += 1
        return messages


def _extract_text(message: dict) -> str | None:
    content = message.get("content")
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    parts.append(block.get("content", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts) if parts else None
    return str(content)
