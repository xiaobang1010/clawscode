from __future__ import annotations

import asyncio
import json

from src.hooks.types import HookContext, HookDefinition, HookResult


class AgentHook:
    @staticmethod
    async def execute(hook: HookDefinition, context: HookContext) -> HookResult:
        from src.tools.agent import _run_agent_loop, _find_agent_definition
        from src.tools import get_tools
        from src.agents.builder import AgentBuilder
        from src.state import Settings

        agent_type = hook.agent_type or "general-purpose"
        definition = _find_agent_definition(agent_type)
        if not definition:
            return HookResult(
                output="",
                error=f"Agent hook: unknown agent type '{agent_type}'",
                should_block=False,
            )

        settings = context.metadata.get("settings") if context.metadata else None
        api_key = ""
        base_url = Settings.base_url
        model = Settings.model
        if settings:
            api_key = getattr(settings, "api_key", "")
            base_url = getattr(settings, "base_url", base_url)
            model = getattr(settings, "model", model)

        model_override = definition.get_model_override()
        if model_override:
            model = model_override

        all_tools = get_tools()
        builder = AgentBuilder(all_tools)
        agent_tools = builder.build_tools(definition)
        system_prompt = builder.build_system_prompt(definition)

        prompt = _build_hook_prompt(hook, context)
        messages = [{"role": "user", "content": prompt}]

        max_turns = min(definition.max_turns, 5)

        try:
            result_text = await asyncio.wait_for(
                _run_agent_loop(
                    messages,
                    agent_tools,
                    system_prompt,
                    model,
                    api_key,
                    base_url,
                    max_turns,
                ),
                timeout=hook.timeout,
            )

            should_block = False
            if result_text.startswith("BLOCK:"):
                should_block = True
                result_text = result_text[6:].strip()

            return HookResult(
                output=result_text,
                should_block=should_block,
            )
        except asyncio.TimeoutError:
            return HookResult(
                error=f"Agent hook timed out after {hook.timeout}s"
            )
        except Exception as e:
            return HookResult(error=f"Agent hook failed: {e}")


def _build_hook_prompt(hook: HookDefinition, context: HookContext) -> str:
    parts = [
        f"Hook event: {context.event.value}",
        f"Hook name: {hook.name}",
    ]

    if context.tool_name:
        parts.append(f"Tool: {context.tool_name}")
    if context.tool_input:
        parts.append(
            f"Tool input: {json.dumps(context.tool_input, ensure_ascii=False, indent=2)}"
        )
    if context.tool_output:
        truncated = context.tool_output
        if len(truncated) > 2000:
            truncated = truncated[:2000] + "\n... (truncated)"
        parts.append(f"Tool output: {truncated}")
    if context.session_id:
        parts.append(f"Session: {context.session_id}")

    extra = {k: v for k, v in context.metadata.items() if k != "settings"}
    if extra:
        parts.append(f"Extra context: {json.dumps(extra, ensure_ascii=False)}")

    parts.append("")
    parts.append(
        "Please process this hook event and provide your response. "
        "If you want to block the operation, start your response with 'BLOCK:'."
    )

    return "\n".join(parts)
