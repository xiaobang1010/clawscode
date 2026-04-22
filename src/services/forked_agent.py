from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from src.api_client import StreamEvent, create_stream
from src.services.agent_context import (
    ContentReplacementState,
    FileStateCache,
    QueryTracking,
    ToolUseContext,
    clone_content_replacement_state,
    clone_file_state_cache,
    create_denial_tracking_state,
    create_query_tracking,
)
from src.services.cache_params import CacheSafeParams, cache_params_match
from src.services.sidechain_storage import record_sidechain_transcript
from src.services.token_counter import count_tokens
from src.tool import Tool, ToolResult


@dataclass
class ForkedAgentParams:
    prompt_messages: list[dict]
    cache_safe_params: CacheSafeParams
    can_use_tool: Any | None = None
    query_source: str = "fork"
    fork_label: str = "fork"
    overrides: dict[str, Any] | None = None
    max_output_tokens: int | None = None
    max_turns: int | None = None
    on_message: Any | None = None
    skip_transcript: bool = True
    skip_cache_write: bool = False


@dataclass
class ForkedAgentResult:
    messages: list[dict]
    total_usage: dict[str, int]
    duration_ms: int
    cache_hit: bool = False


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


def accumulate_usage(total: Usage, delta: Usage) -> Usage:
    return Usage(
        input_tokens=total.input_tokens + delta.input_tokens,
        output_tokens=total.output_tokens + delta.output_tokens,
        cache_read_input_tokens=total.cache_read_input_tokens + delta.cache_read_input_tokens,
        cache_creation_input_tokens=total.cache_creation_input_tokens + delta.cache_creation_input_tokens,
    )


def update_usage(usage: Usage, data: dict) -> Usage:
    return Usage(
        input_tokens=usage.input_tokens + data.get("input_tokens", 0),
        output_tokens=usage.output_tokens + data.get("output_tokens", 0),
        cache_read_input_tokens=usage.cache_read_input_tokens + data.get("cache_read_input_tokens", 0),
        cache_creation_input_tokens=usage.cache_creation_input_tokens + data.get("cache_creation_input_tokens", 0),
    )


def create_subagent_context_from_params(
    cache_safe_params: CacheSafeParams,
    overrides: dict[str, Any] | None = None,
) -> ToolUseContext:
    overrides = overrides or {}

    return ToolUseContext(
        read_file_state=clone_file_state_cache(overrides.get("read_file_state")),
        nested_memory_attachment_triggers=set(),
        loaded_nested_memory_paths=set(),
        dynamic_skill_dir_triggers=set(),
        discovered_skill_names=set(),
        tool_decisions=None,
        content_replacement_state=clone_content_replacement_state(overrides.get("content_replacement_state")),
        abort_controller=overrides.get("abort_controller"),
        get_app_state=overrides.get("get_app_state"),
        set_app_state=overrides.get("set_app_state", lambda: None),
        set_app_state_for_tasks=overrides.get("set_app_state_for_tasks"),
        local_denial_tracking=create_denial_tracking_state(),
        set_in_progress_tool_use_ids=lambda: None,
        set_response_length=lambda: None,
        push_api_metrics_entry=None,
        update_file_history_state=lambda: None,
        update_attribution_state=lambda: None,
        add_notification=None,
        set_tool_jsx=None,
        set_stream_mode=None,
        set_sdk_status=None,
        open_message_selector=None,
        options=overrides.get("options", {}),
        messages=overrides.get("messages", []),
        agent_id=str(uuid.uuid4())[:8],
        agent_type=overrides.get("agent_type"),
        query_tracking=create_query_tracking(),
        file_reading_limits=overrides.get("file_reading_limits", {}),
        user_modified=False,
        critical_system_reminder_experimental=overrides.get("critical_system_reminder"),
        require_can_use_tool=overrides.get("require_can_use_tool", False),
    )


def extract_result_text(messages: list[dict], default_text: str = "执行完成") -> str:
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text.strip():
                            return text
    return default_text


def log_fork_agent_query_event(
    fork_label: str,
    query_source: str,
    duration_ms: int,
    message_count: int,
    total_usage: Usage,
    query_tracking: QueryTracking | None = None,
) -> None:
    total_input_tokens = (
        total_usage.input_tokens +
        total_usage.cache_creation_input_tokens +
        total_usage.cache_read_input_tokens
    )
    cache_hit_rate = (
        total_usage.cache_read_input_tokens / total_input_tokens
        if total_input_tokens > 0 else 0
    )

    print(
        f"[Fork Agent] {fork_label}: "
        f"duration={duration_ms}ms, "
        f"messages={message_count}, "
        f"input={total_usage.input_tokens}, "
        f"output={total_usage.output_tokens}, "
        f"cache_read={total_usage.cache_read_input_tokens}, "
        f"cache_hit_rate={cache_hit_rate:.2%}"
    )


async def run_forked_agent(
    params: ForkedAgentParams,
    tools: list[Tool],
    model: str = "",
    api_key: str = "",
    base_url: str = "",
) -> ForkedAgentResult:
    start_time = time.time()
    output_messages: list[dict] = []
    total_usage = Usage()

    cache_safe_params = params.cache_safe_params
    tool_schemas = [t.get_openai_tool_schema() for t in tools]
    tool_map = {t.name: t for t in tools}

    isolated_context = create_subagent_context_from_params(
        cache_safe_params,
        params.overrides,
    )

    initial_messages = list(cache_safe_params.fork_context_messages) + list(params.prompt_messages)

    max_turns = params.max_turns or 20
    current_usage = Usage()

    try:
        for turn in range(max_turns):
            has_tool_calls = False
            current_tool_calls: dict[int, dict] = {}
            text_parts: list[str] = []

            async for event in create_stream(
                initial_messages,
                tool_schemas,
                cache_safe_params.system_prompt,
                model=model or cache_safe_params.model,
                api_key=api_key or cache_safe_params.api_key,
                base_url=base_url or cache_safe_params.base_url,
            ):
                if event.type == "text_delta":
                    text_parts.append(event.data.get("text", ""))
                elif event.type == "tool_calls":
                    has_tool_calls = True
                    idx = event.data.get("index", 0)
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {
                            "id": event.data["id"],
                            "name": event.data["name"],
                            "arguments": "",
                        }
                    current_tool_calls[idx]["arguments"] += event.data.get("arguments") or ""
                elif event.type == "usage":
                    current_usage = update_usage(current_usage, event.data)

            if not has_tool_calls:
                if text_parts:
                    output_messages.append({
                        "role": "assistant",
                        "content": "".join(text_parts),
                    })
                break

            assistant_content = []
            for idx in sorted(current_tool_calls):
                tc = current_tool_calls[idx]
                assistant_content.append({
                    "type": "function",
                    "id": tc["id"],
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                })

            import json as _json

            async def _exec_tool(tc: dict) -> tuple[dict, str]:
                tool = tool_map.get(tc["name"])
                if not tool:
                    return tc, f"未知工具: {tc['name']}"
                try:
                    tool_input = tool.input_schema(**_json.loads(tc["arguments"]))
                    result = await tool.call(tool_input, isolated_context)
                    return tc, result.output
                except Exception as e:
                    return tc, f"工具执行错误: {e}"

            sorted_tcs = [current_tool_calls[idx] for idx in sorted(current_tool_calls)]
            import asyncio
            results = await asyncio.gather(*[_exec_tool(tc) for tc in sorted_tcs])

            initial_messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": assistant_content,
            })

            for tc, output in results:
                initial_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": output,
                })

            total_usage = accumulate_usage(total_usage, current_usage)
            current_usage = Usage()

    finally:
        isolated_context.read_file_state.clear()

    duration_ms = int((time.time() - start_time) * 1000)

    if not params.skip_transcript and output_messages:
        try:
            record_sidechain_transcript(
                messages=output_messages,
                agent_id=isolated_context.agent_id,
                parent_session_id=params.cache_safe_params.session_id,
            )
        except Exception:
            pass

    log_fork_agent_query_event(
        fork_label=params.fork_label,
        query_source=params.query_source,
        duration_ms=duration_ms,
        message_count=len(output_messages),
        total_usage=total_usage,
        query_tracking=isolated_context.query_tracking,
    )

    cache_hit = total_usage.cache_read_input_tokens > 0

    return ForkedAgentResult(
        messages=output_messages,
        total_usage={
            "input_tokens": total_usage.input_tokens,
            "output_tokens": total_usage.output_tokens,
            "cache_read_input_tokens": total_usage.cache_read_input_tokens,
            "cache_creation_input_tokens": total_usage.cache_creation_input_tokens,
        },
        duration_ms=duration_ms,
        cache_hit=cache_hit,
    )
