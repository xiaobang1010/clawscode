from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from src.api_client import StreamEvent, create_stream
from src.tool import PermissionResult, Tool, ToolResult


async def ask_user_permission(tool: Tool, tool_input: Any, context: Any) -> ToolResult | None:
    print(f"\n[权限请求] {tool.name} 想要执行：{tool_input}")
    answer = input("允许？(y/n/a=always): ").strip().lower()
    if answer in ("y", "a"):
        return await tool.call(tool_input, context)
    return None


async def create_query_loop(
    user_messages: list[dict],
    tools: list[Tool],
    context: Any,
    history: list[dict],
    system_prompt: str,
) -> AsyncGenerator[StreamEvent, None]:
    messages = list(history) + user_messages

    while True:
        tool_schemas = [t.get_openai_tool_schema() for t in tools]
        tool_map = {t.name: t for t in tools}

        has_tool_calls = False
        current_tool_calls: dict[int, dict] = {}

        async for event in create_stream(
            messages,
            tool_schemas,
            system_prompt,
            model=context.settings.model,
            api_key=context.settings.api_key,
            base_url=context.settings.base_url,
        ):
            yield event

            if event.type == "tool_calls":
                has_tool_calls = True
                idx = event.data.get("index", 0)
                if idx not in current_tool_calls:
                    current_tool_calls[idx] = {
                        "id": event.data["id"],
                        "name": event.data["name"],
                        "arguments": "",
                    }
                current_tool_calls[idx]["arguments"] += event.data.get("arguments", "")

        if not has_tool_calls:
            break

        assistant_content = []
        for idx in sorted(current_tool_calls):
            tc = current_tool_calls[idx]
            assistant_content.append(
                {
                    "type": "function",
                    "id": tc["id"],
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
            )

            tool = tool_map[tc["name"]]
            tool_input = tool.input_schema(**json.loads(tc["arguments"]))

            perm = await tool.check_permissions(tool_input, context)
            if perm == PermissionResult.DENY:
                result = ToolResult(output="操作被拒绝", is_error=True)
            elif perm == PermissionResult.ASK:
                result = await ask_user_permission(tool, tool_input, context)
                if result is None:
                    result = ToolResult(output="用户拒绝了操作", is_error=True)
            else:
                result = await tool.call(tool_input, context)

            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": assistant_content,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result.output,
                }
            )
