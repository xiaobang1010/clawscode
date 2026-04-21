from __future__ import annotations

import asyncio

from src.hooks.types import HookContext, HookDefinition, HookResult, HookType
from src.hooks.registry import HookRegistry
from src.hooks.prompt_hook import PromptHook
from src.hooks.agent_hook import AgentHook
from src.hooks.http_hook import HttpHook


class HookExecutor:
    def __init__(self, registry: HookRegistry) -> None:
        self._registry = registry

    async def execute(self, context: HookContext) -> list[HookResult]:
        hooks = self._registry.find_by_event(context.event)
        if not hooks:
            return []

        results = []
        for hook in hooks:
            result = await self._execute_one(hook, context)
            results.append(result)
            if result.should_block:
                break

        return results

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
