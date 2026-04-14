from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tool import Tool
from src.services.prompt_builder import build_system_prompt, PromptBuilder
from src.services.context_provider import ContextProvider
from src.services.claude_md import ClaudeMdDiscovery
from src.services.memory import MemoryDiscovery


def build_context(
    cwd: Path,
    tools: list[Tool],
    custom_instructions: str = "",
    agent_config: dict[str, Any] | None = None,
    is_coordinator: bool = False,
    override_prompt: str = "",
) -> str:
    provider = ContextProvider(cwd)
    env = provider.get_environment_info()
    env_info = provider.format_environment_info(env)

    claude_md = ClaudeMdDiscovery(cwd)
    claude_md_content = claude_md.load_for_system_prompt()

    memory = MemoryDiscovery(cwd)
    memory_content = memory.load_for_system_prompt()

    if claude_md_content:
        custom_parts = [custom_instructions] if custom_instructions else []
        custom_parts.append(claude_md_content)
        if memory_content:
            custom_parts.append(memory_content)
        custom_instructions = "\n\n".join(custom_parts)
    elif memory_content:
        custom_parts = [custom_instructions] if custom_instructions else []
        custom_parts.append(memory_content)
        custom_instructions = "\n\n".join(custom_parts)

    return build_system_prompt(
        cwd=cwd,
        tools=tools,
        environment_info=env_info,
        custom_instructions=custom_instructions,
        agent_config=agent_config,
        is_coordinator=is_coordinator,
        override_prompt=override_prompt,
    )
