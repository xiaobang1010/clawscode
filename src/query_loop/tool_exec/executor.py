from __future__ import annotations

import asyncio
import json
from typing import Any

from src.hooks.types import HookEvent
from src.hooks.executor import HookExecutor
from src.permissions import PermissionChecker
from src.state import SessionState
from src.tool import PermissionResult, Tool, ToolResult
from src.utils.git import is_git_repo, has_changes, create_checkpoint
from src.query_loop.tool_exec.hooks import create_hook_context, ask_user_permission


async def execute_tools(
    tool_calls: list[dict],
    tool_map: dict[str, Tool],
    context: Any,
    permission_checker: PermissionChecker | None,
    hook_executor: HookExecutor | None,
) -> list[tuple[dict, ToolResult]]:

    async def _execute_one(tc: dict) -> tuple[dict, ToolResult]:
        tool = tool_map.get(tc["name"])
        if tool is None:
            return tc, ToolResult(
                output=f"工具 '{tc['name']}' 当前不可用（已延迟加载）",
                is_error=True,
            )

        # git checkpoint
        if tool.name in ("FileEdit", "FileWrite"):
            cwd = getattr(context, "cwd", None)
            if cwd is not None and is_git_repo(cwd):
                if has_changes(cwd):
                    context.checkpoint_count += 1
                    create_checkpoint(cwd, context.checkpoint_count)

        # 解析参数
        tool_input = tool.input_schema(**json.loads(tc["arguments"]))

        # pre-tool hook
        if hook_executor is not None:
            pre_ctx = create_hook_context(
                HookEvent.PRE_TOOL_USE, context,
                tool_name=tool.name,
                tool_input=tc.get("parsed_args", json.loads(tc["arguments"])),
            )
            pre_result = await hook_executor.execute_and_collect(pre_ctx)
            if pre_result.should_block:
                return tc, ToolResult(
                    output=f"操作被 Hook 阻止: {pre_result.output}",
                    is_error=True,
                )

        # 权限检查
        if permission_checker is not None:
            perm = await permission_checker.check(tool, tool_input, context)
        else:
            perm = await tool.check_permissions(tool_input, context)

        if perm == PermissionResult.DENY:
            result = ToolResult(output="操作被拒绝", is_error=True)
        elif perm == PermissionResult.ASK:
            context.session_state = SessionState.REQUIRES_ACTION
            result = await ask_user_permission(tool, tool_input, context, permission_checker)
            context.session_state = SessionState.RUNNING
            if result is None:
                result = ToolResult(output="用户拒绝了操作", is_error=True)
        else:
            result = await tool.call(tool_input, context)

        # 结果截断
        max_chars = getattr(tool, "max_result_size_chars", 25000)
        if len(result.output) > max_chars:
            result = result.truncate(max_chars)

        # post-tool hook
        if hook_executor is not None:
            post_ctx = create_hook_context(
                HookEvent.POST_TOOL_USE, context,
                tool_name=tool.name,
                tool_input=json.loads(tc["arguments"]),
                tool_output=result.output,
            )
            await hook_executor.execute(post_ctx)

        return tc, result

    return await asyncio.gather(*[_execute_one(tc) for tc in tool_calls])
