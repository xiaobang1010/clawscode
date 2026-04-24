from __future__ import annotations

import asyncio
import fnmatch
import logging

from src.hooks.types import HookContext, HookDefinition, HookResult, HookType
from src.hooks.registry import HookRegistry
from src.hooks.prompt_hook import PromptHook
from src.hooks.agent_hook import AgentHook
from src.hooks.http_hook import HttpHook

logger = logging.getLogger(__name__)


class HookExecutor:
    def __init__(self, registry: HookRegistry) -> None:
        self._registry = registry

    async def execute(self, context: HookContext) -> list[HookResult]:
        hooks = self._registry.find_by_event(context.event, tool_name=context.tool_name)
        if not hooks:
            return []

        results = []
        hooks_to_remove = []

        for hook in hooks:
            if not self._matches_filters(hook, context):
                continue

            result = await self._execute_one(hook, context)
            results.append(result)

            if hook.once:
                hooks_to_remove.append(hook.name)

            if result.should_block:
                break

        for name in hooks_to_remove:
            self._registry.unregister(name)

        return results

    def _matches_filters(self, hook: HookDefinition, context: HookContext) -> bool:
        if hook.matcher:
            if not _matches_matcher(hook.matcher, context.tool_name):
                return False

        if hook.if_condition:
            if not _matches_if_condition(hook.if_condition, context.tool_name, context.tool_input):
                return False

        return True

    async def _execute_one(self, hook: HookDefinition, context: HookContext) -> HookResult:
        try:
            if hook.hook_type == HookType.PROMPT:
                return await PromptHook.execute(hook, context)
            elif hook.hook_type == HookType.HTTP:
                return await HttpHook.execute(hook, context)
            elif hook.hook_type == HookType.AGENT:
                return await AgentHook.execute(hook, context)
            return HookResult(error=f"Unknown hook type: {hook.hook_type}")
        except asyncio.TimeoutError:
            return HookResult(error=f"Hook '{hook.name}' timed out after {hook.timeout}s")
        except Exception as e:
            return HookResult(error=f"Hook '{hook.name}' failed: {e}")

    async def execute_and_collect(self, context: HookContext) -> HookResult:
        results = await self.execute(context)
        if not results:
            return HookResult()

        combined_output = "\n".join(r.output for r in results if r.output)
        errors = [r.error for r in results if r.error]
        should_block = any(r.should_block for r in results)
        prevent_continuation = any(r.prevent_continuation for r in results)

        return HookResult(
            output=combined_output,
            error="; ".join(errors) if errors else None,
            should_block=should_block,
            prevent_continuation=prevent_continuation,
        )


def _matches_matcher(matcher: str, tool_name: str) -> bool:
    if not tool_name:
        return False
    return fnmatch.fnmatch(tool_name, matcher) or matcher == tool_name


def _matches_if_condition(if_condition: str, tool_name: str, tool_input: dict) -> bool:
    if ":" not in if_condition:
        return fnmatch.fnmatch(tool_name, if_condition)

    rule_tool, _, rule_pattern = if_condition.partition(":")
    if not fnmatch.fnmatch(tool_name, rule_tool) and rule_tool != tool_name:
        return False

    if rule_pattern == "*":
        return True

    input_str = str(tool_input)
    return fnmatch.fnmatch(input_str, rule_pattern) or any(
        fnmatch.fnmatch(str(v), rule_pattern)
        for v in tool_input.values()
    )
