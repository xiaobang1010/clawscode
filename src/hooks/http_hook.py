from __future__ import annotations

import asyncio
import json

from src.hooks.types import HookContext, HookDefinition, HookResult


class HttpHook:
    @staticmethod
    async def execute(hook: HookDefinition, context: HookContext) -> HookResult:
        try:
            import httpx
        except ImportError:
            return HookResult(error="httpx is required for HTTP hooks")

        payload = {
            "event": context.event.value,
            "tool_name": context.tool_name,
            "tool_input": context.tool_input,
            "tool_output": context.tool_output,
            "session_id": context.session_id,
            "metadata": context.metadata,
        }

        try:
            async with httpx.AsyncClient(timeout=hook.timeout) as client:
                response = await client.post(
                    hook.url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                should_block = response.status_code == 403

                return HookResult(
                    output=response.text,
                    error=None if 200 <= response.status_code < 300 else f"HTTP {response.status_code}",
                    should_block=should_block,
                    metadata={"status_code": response.status_code},
                )
        except Exception as e:
            if "timeout" in str(e).lower():
                raise asyncio.TimeoutError()
            return HookResult(error=f"HTTP hook failed: {e}")
