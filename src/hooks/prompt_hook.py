from __future__ import annotations

import asyncio
import json

from src.hooks.types import HookContext, HookDefinition, HookResult


class PromptHook:
    @staticmethod
    async def execute(hook: HookDefinition, context: HookContext) -> HookResult:
        env_input = json.dumps({
            "event": context.event.value,
            "tool_name": context.tool_name,
            "tool_input": context.tool_input,
            "tool_output": context.tool_output,
            "session_id": context.session_id,
            "metadata": context.metadata,
        }, ensure_ascii=False)

        try:
            proc = await asyncio.create_subprocess_shell(
                hook.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(env_input.encode()),
                timeout=hook.timeout,
            )

            output = stdout.decode("utf-8", errors="replace").strip()
            error = stderr.decode("utf-8", errors="replace").strip() if stderr else None

            should_block = False
            if output.startswith("BLOCK:"):
                should_block = True
                output = output[6:].strip()

            return HookResult(
                output=output,
                error=error if error else None,
                should_block=should_block,
            )
        except asyncio.TimeoutError:
            return HookResult(error=f"Prompt hook timed out after {hook.timeout}s")
        except FileNotFoundError:
            return HookResult(error=f"Command not found: {hook.command}")
        except Exception as e:
            return HookResult(error=f"Prompt hook failed: {e}")
