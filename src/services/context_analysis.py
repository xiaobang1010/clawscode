from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from src.services.token_counter import count_tokens, has_thinking_blocks, count_thinking_tokens


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


@dataclass
class TokenStats:
    total_tokens: int = 0
    user_tokens: int = 0
    assistant_tokens: int = 0
    tool_call_tokens: int = 0
    tool_result_tokens: int = 0
    system_tokens: int = 0
    thinking_tokens: int = 0
    context_window: int = 0
    utilization_percent: float = 0.0
    has_thinking: bool = False


def token_stats_to_metrics(stats: TokenStats) -> dict[str, Any]:
    return {
        "context": {
            "total_tokens": stats.total_tokens,
            "context_window": stats.context_window,
            "free_tokens": max(0, stats.context_window - stats.total_tokens),
            "utilization_percent": stats.utilization_percent,
        },
        "messages": {
            "user_tokens": stats.user_tokens,
            "assistant_tokens": stats.assistant_tokens,
            "tool_call_tokens": stats.tool_call_tokens,
            "tool_result_tokens": stats.tool_result_tokens,
            "system_tokens": stats.system_tokens,
        },
        "thinking": {
            "has_thinking_blocks": stats.has_thinking,
            "thinking_tokens": stats.thinking_tokens,
        },
        "health": {
            "status": _get_health_status(stats.utilization_percent),
            "warnings": _get_warnings(stats),
        },
    }


def _get_health_status(utilization: float) -> str:
    if utilization < 50:
        return "healthy"
    elif utilization < 75:
        return "moderate"
    elif utilization < 90:
        return "high"
    else:
        return "critical"


def _get_warnings(stats: TokenStats) -> list[str]:
    warnings = []

    if stats.utilization_percent > 80:
        warnings.append(f"上下文使用率过高: {stats.utilization_percent:.1f}%")

    if stats.tool_result_tokens > stats.total_tokens * 0.5:
        warnings.append("工具结果占用超过 50% 上下文")

    if stats.thinking_tokens > 10000:
        warnings.append(f"Thinking 块占用大量 tokens: {stats.thinking_tokens}")

    return warnings


def compute_token_stats(
    messages: list[dict],
    system_prompt: str = "",
    context_window: int = 128000,
) -> TokenStats:
    stats = TokenStats(context_window=context_window)
    stats.has_thinking = has_thinking_blocks(messages)
    stats.thinking_tokens = count_thinking_tokens(messages)

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        content_tokens = _estimate_tokens_for_text(str(content) if not isinstance(content, str) else content)

        if role == "user":
            stats.user_tokens += content_tokens
        elif role == "assistant":
            stats.assistant_tokens += content_tokens
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                tc_tokens = _estimate_tokens_for_text(str(tc))
                stats.tool_call_tokens += tc_tokens
        elif role == "tool":
            stats.tool_result_tokens += content_tokens
        elif role == "system":
            stats.system_tokens += content_tokens

    stats.system_tokens += _estimate_tokens_for_text(system_prompt)
    stats.total_tokens = (
        stats.user_tokens +
        stats.assistant_tokens +
        stats.tool_call_tokens +
        stats.tool_result_tokens +
        stats.system_tokens +
        stats.thinking_tokens
    )

    if stats.context_window > 0:
        stats.utilization_percent = round(stats.total_tokens / stats.context_window * 100, 1)

    return stats
