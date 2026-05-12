from __future__ import annotations

from src.query_loop.message.builder import build_tool_calls_content
from src.query_loop.state import QueryState
from src.tool import Tool, ToolResult


def append_assistant_message(
    state: QueryState,
    tool_calls: dict[int, dict],
    has_tool_calls: bool,
) -> None:
    # 将 assistant 消息追加到 state.messages
    state.messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": build_tool_calls_content(tool_calls) if has_tool_calls else None,
        }
    )


def append_tool_results(
    state: QueryState,
    results: list[tuple[dict, ToolResult]],
    tool_map: dict[str, Tool],
) -> None:
    # 更新 active_skill_tools（skill 工具白名单）
    for tc, result in results:
        if result.metadata and "allowed_tools" in result.metadata:
            state.active_skill_tools = result.metadata["allowed_tools"]

    # 追加 tool result 消息
    for tc, result in results:
        state.messages.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result.output,
            }
        )
