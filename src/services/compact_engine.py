from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from src.services.token_counter import count_tokens

AUTOCOMPACT_BUFFER_TOKENS = 13000
WARNING_THRESHOLD_TOKENS = 20000
MAX_CONSECUTIVE_FAILURES = 3
MIN_RECENT_MESSAGES = 10
REACTIVE_COMPACT_MAX_RETRIES = 2

BASE_COMPACT_PROMPT = """你的任务是对迄今为止的对话创建一份详细的摘要，重点关注用户的明确请求和之前的操作。
摘要必须全面捕捉技术细节、代码模式和架构决策，这些对于继续开发工作而不丢失上下文至关重要。

在提供最终摘要之前，将你的分析过程放在 <analysis> 标签中，按以下步骤组织思路：

1. 按时间顺序分析对话中的每条消息和每个部分。对每个部分彻底识别：
   - 用户的明确请求和意图
   - 你处理用户请求的方法
   - 关键决策、技术概念和代码模式
   - 具体细节，如文件名、完整代码片段、函数签名、文件编辑
   - 遇到的错误以及修复方法
   - 特别关注用户给出的反馈，尤其是用户要求你以不同方式做事的情况
2. 仔细检查技术准确性和完整性，确保每个必要元素都被充分覆盖。

摘要必须包含以下 9 个部分：

1. **请求意图**：详细捕获用户的所有明确请求和意图
2. **技术概念**：列出所有讨论的重要技术概念、技术和框架
3. **文件和代码**：枚举检查、修改或创建的具体文件和代码段。特别注意最近的消息，在适用处包含完整代码片段，并说明此文件读取或编辑为何重要
4. **错误和修复**：列出所有遇到的错误以及如何修复它们。特别关注用户反馈
5. **问题解决**：记录已解决的问题和任何正在进行的故障排除工作
6. **用户消息**：列出所有非工具结果的用户消息，这些对理解用户反馈和意图变化至关重要
7. **待办任务**：概述所有已明确要求处理的待办任务
8. **当前工作**：精确描述在此摘要请求之前正在处理的工作，特别注意用户和助手的最近消息。包含文件名和代码片段
9. **下一步**：列出与最近工作直接相关的下一步。包含最近对话中显示你正在处理什么任务以及在哪里中断的直接引用

以下是输出结构的示例：

<example>
<analysis>
[你的思考过程，确保所有要点都被彻底准确地覆盖]
</analysis>

<summary>
1. 请求意图：
   [详细描述]

2. 技术概念：
   - [概念 1]
   - [概念 2]

3. 文件和代码：
   - [文件名 1]
      - [此文件为何重要]
      - [对此文件的更改摘要]
      - [重要代码片段]
   - [文件名 2]
      - [重要代码片段]

4. 错误和修复：
    - [错误 1 的详细描述]:
      - [如何修复]
      - [用户对此错误的反馈]

5. 问题解决：
   [已解决问题的描述和正在进行的故障排除]

6. 用户消息：
    - [详细的非工具使用用户消息]

7. 待办任务：
   - [任务 1]
   - [任务 2]

8. 当前工作：
   [当前工作的精确描述]

9. 下一步：
   [要采取的下一步]
</summary>
</example>

请根据对话内容提供摘要，遵循上述结构并确保精确性和彻底性。

可能包含额外的摘要指令。如果包含，请记住这些指令。"""

PARTIAL_COMPACT_PROMPT = """你的任务是对对话中最近部分的消息创建一份详细的摘要——这些消息在之前保留的上下文之后。之前的消息保持不变，不需要摘要。仅关注最近消息中讨论、学习和完成的内容。

在提供最终摘要之前，将你的分析过程放在 <analysis> 标签中：

1. 按时间顺序分析最近的消息。对每个部分彻底识别：
   - 用户的明确请求和意图
   - 你处理用户请求的方法
   - 关键决策、技术概念和代码模式
   - 具体细节：文件名、代码片段、函数签名、文件编辑
   - 遇到的错误以及修复方法
   - 特别关注用户反馈
2. 仔细检查技术准确性和完整性。

摘要必须包含以下 9 个部分：

1. **请求意图**：从最近消息中捕获用户的明确请求和意图
2. **技术概念**：列出最近讨论的重要技术概念、技术和框架
3. **文件和代码**：枚举检查、修改或创建的文件和代码段
4. **错误和修复**：列出遇到的错误以及如何修复
5. **问题解决**：记录已解决的问题和正在进行的故障排除
6. **用户消息**：列出最近部分所有非工具结果的用户消息
7. **待办任务**：概述最近消息中的待办任务
8. **当前工作**：精确描述在此摘要请求之前正在处理的工作
9. **下一步**：列出与最近工作相关的下一步

请仅根据最近的消息提供摘要，遵循上述结构。"""

NO_TOOLS_PREAMBLE = """关键：仅使用文本回复。不要调用任何工具。

- 不要使用 Read、Bash、Grep、Glob、Edit、Write 或任何其他工具。
- 你已经拥有上方对话中的所有上下文。
- 工具调用将被拒绝并浪费你唯一的轮次——你将无法完成任务。
- 你的整个回复必须是纯文本：一个 <analysis> 块后跟一个 <summary> 块。

"""

NO_TOOLS_TRAILER = "\n\n提醒：不要调用任何工具。仅用纯文本回复——一个 <analysis> 块后跟一个 <summary> 块。工具调用将被拒绝，你将无法完成任务。"

COMPACT_BOUNDARY_PREFIX = "[compact]"


@dataclass
class CompactResult:
    summary: str
    original_token_count: int
    compacted_token_count: int
    messages_removed: int
    is_full: bool


@dataclass
class ContentReplacementState:
    original_chars: int
    replacement_chars: int
    tool_name: str
    message_index: int
    replaced_at: float = field(default_factory=time.time)


MICRO_COMPACT_DEFAULT_MAX_CHARS = 25000
MICRO_COMPACT_PREVIEW_RATIO = 0.4

_consecutive_failures = 0
_micro_replacement_log: list[ContentReplacementState] = []


def get_micro_replacement_log() -> list[ContentReplacementState]:
    return list(_micro_replacement_log)


def clear_micro_replacement_log() -> None:
    _micro_replacement_log.clear()


def micro_compact(
    messages: list[dict],
    max_chars: int = MICRO_COMPACT_DEFAULT_MAX_CHARS,
) -> list[dict]:
    global _micro_replacement_log

    result = []
    replacements: list[ContentReplacementState] = []
    changed = False

    for idx, msg in enumerate(messages):
        if msg.get("role") != "tool":
            result.append(msg)
            continue

        content = msg.get("content", "")
        if not isinstance(content, str) or len(content) <= max_chars:
            result.append(msg)
            continue

        original_len = len(content)

        head_chars = int(max_chars * MICRO_COMPACT_PREVIEW_RATIO)
        tail_chars = max_chars - head_chars - 200

        head = content[:head_chars]
        tail = content[-tail_chars:] if tail_chars > 0 else ""

        tool_name = msg.get("name", msg.get("tool_call_id", "unknown"))
        summary = (
            f"{head}\n\n"
            f"...[Micro Compact: 工具结果已压缩，原始 {original_len} 字符 → "
            f"压缩后约 {max_chars} 字符，工具: {tool_name}]...\n\n"
            f"{tail}"
        )

        new_msg = dict(msg)
        new_msg["content"] = summary
        if "_original_content_length" not in new_msg:
            new_msg["_original_content_length"] = original_len
        result.append(new_msg)

        replacements.append(ContentReplacementState(
            original_chars=original_len,
            replacement_chars=len(summary),
            tool_name=tool_name,
            message_index=idx,
        ))
        changed = True

    if changed:
        _micro_replacement_log = _micro_replacement_log + replacements

    return result


def format_compact_summary(summary: str) -> str:
    formatted = summary
    formatted = re.sub(r'<analysis>[\s\S]*?</analysis>', '', formatted)
    summary_match = re.search(r'<summary>([\s\S]*?)</summary>', formatted)
    if summary_match:
        content = summary_match.group(1) or ''
        formatted = re.sub(
            r'<summary>[\s\S]*?</summary>',
            f'摘要:\n{content.strip()}',
            formatted,
        )
    formatted = re.sub(r'\n\n+', '\n\n', formatted)
    return formatted.strip()


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

    prompt = NO_TOOLS_PREAMBLE + BASE_COMPACT_PROMPT
    if custom_instructions:
        prompt += f"\n\n额外压缩指令：{custom_instructions}"
    prompt += NO_TOOLS_TRAILER

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

    prompt = NO_TOOLS_PREAMBLE + PARTIAL_COMPACT_PROMPT + NO_TOOLS_TRAILER

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


def create_compact_boundary_message(summary: str, original_count: int, compacted_count: int) -> dict:
    formatted = format_compact_summary(summary)
    return {
        "role": "user",
        "content": (
            f"{COMPACT_BOUNDARY_PREFIX} 上下文压缩完成。\n"
            f"原始消息约 {original_count} tokens，压缩后约 {compacted_count} tokens。\n"
            f"摘要：\n{formatted}"
        ),
    }


def is_compact_boundary(message: dict) -> bool:
    content = _extract_text(message)
    return content is not None and content.startswith(COMPACT_BOUNDARY_PREFIX)


def apply_compaction(
    messages: list[dict],
    summary: str,
    keep_recent: int = MIN_RECENT_MESSAGES,
    preserved_from: int = 0,
) -> list[dict]:
    global _consecutive_failures

    system = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    original_count = len(non_system)

    formatted_summary = format_compact_summary(summary)
    boundary = create_compact_boundary_message(
        formatted_summary,
        count_tokens(non_system),
        count_tokens([{"role": "user", "content": formatted_summary}]),
    )

    if preserved_from > 0 and preserved_from < len(non_system):
        to_compress = non_system[:-preserved_from]
        preserved = non_system[-preserved_from:]
        if len(to_compress) <= keep_recent:
            kept = non_system
        else:
            kept = to_compress[-keep_recent:] + preserved
    elif len(non_system) <= keep_recent:
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
            NO_TOOLS_PREAMBLE.strip(),
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


async def reactive_compact(
    messages: list[dict],
    max_tokens: int,
    create_stream_fn: Any = None,
    max_retries: int = REACTIVE_COMPACT_MAX_RETRIES,
) -> list[dict]:
    for attempt in range(max_retries):
        result = await compact_with_llm(messages, max_tokens, create_stream_fn)
        used = count_tokens(result)
        if used <= max_tokens:
            return result

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

        boundary = create_compact_boundary_message(
            f"[自动截断] 移除了 {len(non_system) - recent_count} 条旧消息以节省空间。",
            count_tokens(non_system),
            count_tokens(system + non_system[-recent_count:]),
        )
        compacted = system + [boundary] + non_system[-recent_count:]
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


SM_COMPACT_MIN_TOKENS = 10_000
SM_COMPACT_MIN_TEXT_MESSAGES = 5
SM_COMPACT_MAX_TOKENS = 40_000

_last_summarized_message_id: str | None = None


def set_last_summarized_message_id(msg_id: str | None) -> None:
    global _last_summarized_message_id
    _last_summarized_message_id = msg_id


def get_last_summarized_message_id() -> str | None:
    return _last_summarized_message_id


def _has_text_content(message: dict) -> bool:
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return True
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
                return True
    return False


def _count_text_block_messages(messages: list[dict]) -> int:
    return sum(1 for m in messages if m.get("role") in ("user", "assistant") and _has_text_content(m))


def calculate_messages_to_keep_index(
    messages: list[dict],
    min_tokens: int = SM_COMPACT_MIN_TOKENS,
    min_text_messages: int = SM_COMPACT_MIN_TEXT_MESSAGES,
    max_tokens: int = SM_COMPACT_MAX_TOKENS,
) -> int:
    non_system = [m for m in messages if m.get("role") != "system"]
    if not non_system:
        return 0

    start_idx = 0
    if _last_summarized_message_id is not None:
        for i, m in enumerate(non_system):
            if m.get("id") == _last_summarized_message_id or m.get("_message_id") == _last_summarized_message_id:
                start_idx = i + 1
                break

    candidates = non_system[start_idx:]
    if not candidates:
        return len(non_system)

    best_idx = len(non_system)

    for n in range(1, len(candidates) + 1):
        window = candidates[-n:]
        tokens = count_tokens(window)
        text_count = _count_text_block_messages(window)

        if tokens >= min_tokens and text_count >= min_text_messages:
            best_idx = len(non_system) - n
            if tokens > max_tokens:
                best_idx = len(non_system) - n + 1
            break

    return best_idx


def _adjust_index_to_preserve_pairs(messages: list[dict], idx: int) -> int:
    if idx <= 0 or idx >= len(messages):
        return idx

    non_system = [m for m in messages if m.get("role") != "system"]
    actual_idx = idx

    if actual_idx < len(non_system):
        msg = non_system[actual_idx]
        prev_msg = non_system[actual_idx - 1] if actual_idx > 0 else None

        if msg.get("role") == "tool" and prev_msg and prev_msg.get("tool_calls"):
            has_matching_call = False
            tool_id = msg.get("tool_call_id")
            for tc in (prev_msg.get("tool_calls") or []):
                if tc.get("id") == tool_id:
                    has_matching_call = True
                    break
            if not has_matching_call:
                actual_idx -= 1

    return actual_idx


def session_memory_compact(messages: list[dict]) -> list[dict]:
    system = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    if len(non_system) <= MIN_RECENT_MESSAGES:
        return messages

    keep_from = calculate_messages_to_keep_index(messages)
    keep_from = _adjust_index_to_preserve_pairs(messages, keep_from)

    if keep_from <= 0:
        return messages

    to_remove = non_system[:keep_from]
    to_keep = non_system[keep_from:]

    boundary = create_compact_boundary_message(
        f"[Session Memory Compact] 保留了最近 {len(to_keep)} 条消息（{count_tokens(to_keep)} tokens）。"
        f"移除了 {len(to_remove)} 条旧消息，无需 LLM 调用。",
        count_tokens(to_remove),
        count_tokens(to_keep),
    )

    if to_keep and to_keep[0].get("id"):
        set_last_summarized_message_id(to_keep[0].get("id") or to_keep[0].get("_message_id"))

    return system + [boundary] + to_keep


async def auto_compact_with_priority(
    messages: list[dict],
    max_tokens: int,
    create_stream_fn: Any = None,
) -> list[dict]:
    used = count_tokens(messages)
    if used <= max_tokens * 0.8:
        return messages

    result = session_memory_compact(messages)
    result_tokens = count_tokens(result)
    if result_tokens <= max_tokens * 0.9:
        return _inject_post_compact_context(result)

    compacted = await compact_with_llm(messages, max_tokens, create_stream_fn)
    return _inject_post_compact_context(compacted)


def _inject_post_compact_context(messages: list[dict]) -> list[dict]:
    return _restore_recent_file_reads(messages)


def _restore_recent_file_reads(messages: list[dict], max_files: int = 5, max_chars_per_file: int = 5000) -> list[dict]:
    file_reads: dict[str, str] = {}
    for msg in reversed(messages):
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 100:
                tool_call_id = msg.get("tool_call_id", "")
                for m in messages:
                    if m.get("tool_calls"):
                        for tc in m.get("tool_calls", []):
                            if tc.get("id") == tool_call_id:
                                args_str = tc.get("function", {}).get("arguments", "")
                                if "file_path" in args_str or "path" in args_str:
                                    try:
                                        import json
                                        args = json.loads(args_str)
                                        fp = args.get("file_path") or args.get("path", "")
                                        if fp and fp not in file_reads:
                                            file_reads[fp] = content[:max_chars_per_file]
                                            if len(file_reads) >= max_files:
                                                break
                                    except (json.JSONDecodeError, KeyError):
                                        pass
        if len(file_reads) >= max_files:
            break

    if not file_reads:
        return messages

    injection_lines = ["[压缩后恢复] 以下文件内容在压缩前被读取，已恢复供参考：\n"]
    for fp, content in list(file_reads.items())[:max_files]:
        truncated = content[:max_chars_per_file]
        if len(content) > max_chars_per_file:
            truncated += f"\n...[截断，共 {len(content)} 字符]"
        injection_lines.append(f"--- {fp} ---\n{truncated}\n")

    injection_msg = {
        "role": "user",
        "content": "\n".join(injection_lines),
        "_post_compact_injection": True,
    }

    system = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    boundary_idx = 0
    for i, m in enumerate(non_system):
        if is_compact_boundary(m):
            boundary_idx = i
            break

    result = system + non_system[:boundary_idx + 1] + [injection_msg] + non_system[boundary_idx + 1:]
    return result
