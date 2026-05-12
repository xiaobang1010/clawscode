from __future__ import annotations

from typing import Any

from src.hooks.types import HookContext, HookEvent
from src.hooks.executor import HookExecutor
from src.permissions import PermissionChecker
from src.tool import Tool, ToolResult


def create_hook_context(
    event: HookEvent,
    context: Any,
    tool_name: str = "",
    tool_input: dict | None = None,
    tool_output: str = "",
) -> HookContext:
    return HookContext(
        event=event,
        tool_name=tool_name,
        tool_input=tool_input or {},
        tool_output=tool_output,
        session_id=getattr(context, "session_id", ""),
        messages=getattr(context, "messages", []),
    )


async def execute_stop_hooks(
    hook_executor: HookExecutor,
    context: Any,
) -> dict[str, Any]:
    stop_ctx = create_hook_context(HookEvent.STOP, context)
    results = await hook_executor.execute(stop_ctx)

    blocking_error = ""
    prevent_continuation = False

    for result in results:
        if result.should_block:
            if result.output:
                blocking_error += result.output + "\n"
            if result.metadata.get("prevent_continuation"):
                prevent_continuation = True

    return {
        "blocking_error": blocking_error.strip(),
        "prevent_continuation": prevent_continuation,
    }


async def ask_user_permission(
    tool: Tool,
    tool_input: Any,
    context: Any,
    permission_checker: PermissionChecker | None = None,
) -> ToolResult | None:
    print(f"\n[权限请求] {tool.name} 想要执行：{tool_input}")
    answer = input("允许？(y/n/a=always): ").strip().lower()
    if answer == "a":
        if permission_checker is not None:
            permission_checker.add_allow_rule(f"{tool.name}:*")
        return await tool.call(tool_input, context)
    elif answer == "y":
        return await tool.call(tool_input, context)
    return None
