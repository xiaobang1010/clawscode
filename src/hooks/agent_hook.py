from __future__ import annotations

from src.hooks.types import HookContext, HookDefinition, HookResult


class AgentHook:
    @staticmethod
    async def execute(hook: HookDefinition, context: HookContext) -> HookResult:
        return HookResult(
            output="",
            error="Agent hooks require agent_runtime integration",
            should_block=False,
        )
