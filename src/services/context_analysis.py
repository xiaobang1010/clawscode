from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from src.services.token_counter import count_tokens


@dataclass
class ContextCategory:
    name: str
    tokens: int = 0
    percentage: float = 0.0


@dataclass
class MessageBreakdown:
    tool_call_tokens: int = 0
    tool_result_tokens: int = 0
    attachment_tokens: int = 0
    assistant_message_tokens: int = 0
    user_message_tokens: int = 0


@dataclass
class DuplicateRead:
    file_path: str
    read_count: int
    total_tokens: int
    wasted_tokens: int = 0


@dataclass
class ContextData:
    categories: list[ContextCategory] = field(default_factory=list)
    message_breakdown: MessageBreakdown = field(default_factory=MessageBreakdown)
    duplicate_reads: list[DuplicateRead] = field(default_factory=list)
    total_tokens: int = 0
    free_tokens: int = 0
    context_window: int = 0


def _estimate_tokens_for_text(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _extract_file_path_from_args(args_str: str) -> str:
    import json
    try:
        args = json.loads(args_str)
        return args.get("file_path") or args.get("path") or args.get("pattern") or ""
    except (json.JSONDecodeError, KeyError):
        return ""


def analyze_context_usage(
    messages: list[dict],
    system_prompt: str = "",
    tools_schema: list[dict] | None = None,
    context_window: int = 128000,
) -> ContextData:
    data = ContextData(context_window=context_window)

    system_tokens = _estimate_tokens_for_text(system_prompt)
    data.categories.append(ContextCategory(name="System Prompt", tokens=system_tokens))

    tools_tokens = 0
    if tools_schema:
        import json
        tools_tokens = _estimate_tokens_for_text(json.dumps(tools_schema))
    data.categories.append(ContextCategory(name="Tools Schema", tokens=tools_tokens))

    breakdown = MessageBreakdown()
    tool_requests_by_name: dict[str, int] = defaultdict(int)
    file_read_tracker: dict[str, list[int]] = defaultdict(list)

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        content_tokens = _estimate_tokens_for_text(str(content) if not isinstance(content, str) else content)

        if role == "user":
            breakdown.user_message_tokens += content_tokens
        elif role == "assistant":
            breakdown.assistant_message_tokens += content_tokens
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                tc_tokens = _estimate_tokens_for_text(str(tc))
                breakdown.tool_call_tokens += tc_tokens
                fn_name = tc.get("function", {}).get("name", "")
                tool_requests_by_name[fn_name] += 1

                if fn_name in ("FileRead", "Read"):
                    args_str = tc.get("function", {}).get("arguments", "")
                    fp = _extract_file_path_from_args(args_str)
                    if fp:
                        file_read_tracker[fp].append(tc_tokens)
        elif role == "tool":
            breakdown.tool_result_tokens += content_tokens

    data.categories.append(ContextCategory(name="User Messages", tokens=breakdown.user_message_tokens))
    data.categories.append(ContextCategory(name="Assistant Messages", tokens=breakdown.assistant_message_tokens))
    data.categories.append(ContextCategory(name="Tool Calls", tokens=breakdown.tool_call_tokens))
    data.categories.append(ContextCategory(name="Tool Results", tokens=breakdown.tool_result_tokens))

    data.message_breakdown = breakdown

    for fp, token_list in file_read_tracker.items():
        if len(token_list) > 1:
            total = sum(token_list)
            data.duplicate_reads.append(DuplicateRead(
                file_path=fp,
                read_count=len(token_list),
                total_tokens=total,
                wasted_tokens=token_list[-1],
            ))

    data.total_tokens = sum(c.tokens for c in data.categories)
    data.free_tokens = max(0, context_window - data.total_tokens)

    if data.total_tokens > 0:
        for cat in data.categories:
            cat.percentage = round(cat.tokens / data.total_tokens * 100, 1)

    return data


def format_context_report(data: ContextData) -> str:
    lines = ["=" * 50, "  上下文使用分析报告", "=" * 50, ""]

    lines.append(f"上下文窗口: {data.context_window:,} tokens")
    lines.append(f"已使用: {data.total_tokens:,} tokens ({data.total_tokens / max(1, data.context_window) * 100:.1f}%)")
    lines.append(f"剩余: {data.free_tokens:,} tokens")
    lines.append("")

    lines.append("--- Token 分布 ---")
    bar_width = 30
    for cat in data.categories:
        bar_len = int(cat.percentage / 100 * bar_width) if data.total_tokens > 0 else 0
        bar = "█" * bar_len + "░" * (bar_width - bar_len)
        lines.append(f"  {cat.name:<20} {bar} {cat.tokens:>6,} ({cat.percentage:.1f}%)")

    lines.append("")
    lines.append("--- 消息分类 ---")
    bd = data.message_breakdown
    lines.append(f"  用户消息:    {bd.user_message_tokens:>6,} tokens")
    lines.append(f"  助手消息:    {bd.assistant_message_tokens:>6,} tokens")
    lines.append(f"  工具调用:    {bd.tool_call_tokens:>6,} tokens")
    lines.append(f"  工具结果:    {bd.tool_result_tokens:>6,} tokens")

    if data.duplicate_reads:
        lines.append("")
        lines.append("--- 重复文件读取 ---")
        for dr in data.duplicate_reads[:10]:
            lines.append(f"  {dr.file_path}: 读取 {dr.read_count} 次，浪费约 {dr.wasted_tokens} tokens")

    lines.append("")
    lines.append("=" * 50)
    return "\n".join(lines)
