from __future__ import annotations

from typing import Any

from src.agents.agent_definition import AgentDefinition
from src.services.prompt_builder import PromptBuilder
from src.tool import Tool


class AgentBuilder:
    def __init__(self, all_tools: list[Tool], base_system_prompt: str = ""):
        self._all_tools = all_tools
        self._tool_map: dict[str, Tool] = {t.name: t for t in all_tools}
        self._base_system_prompt = base_system_prompt

    def build_tools(self, definition: AgentDefinition) -> list[Tool]:
        allowed = definition.get_allowed_tools()
        disallowed = definition.get_disallowed_tools()

        if allowed:
            tools = [self._tool_map[n] for n in allowed if n in self._tool_map]
        else:
            tools = list(self._all_tools)

        if disallowed:
            tools = [t for t in tools if t.name not in disallowed]

        return [t for t in tools if t.is_available()]

    def build_system_prompt(
        self,
        definition: AgentDefinition,
        environment_info: str = "",
        custom_instructions: str = "",
    ) -> str:
        tools = self.build_tools(definition)
        builder = PromptBuilder(
            cwd=getattr(self, "_cwd", None) or __import__("pathlib").Path.cwd(),
            tools=tools,
        )

        if custom_instructions:
            builder.set_custom_instructions(custom_instructions)

        builder.set_agent_config(
            name=definition.name,
            agent_type=definition.agent_type.value,
            when_to_use=definition.when_to_use,
            allowed_tools=[t.name for t in tools],
            disallowed_tools=definition.disallowed_tools,
        )

        if definition.system_prompt and not definition.system_prompt_append:
            builder.set_override(definition.system_prompt)
        elif definition.system_prompt:
            builder.set_custom_instructions(
                (custom_instructions + "\n\n" + definition.system_prompt).strip()
            )

        return builder.build(environment_info=environment_info)

    def build_agent_config(self, definition: AgentDefinition) -> dict[str, Any]:
        return {
            "name": definition.name,
            "agent_type": definition.agent_type.value,
            "when_to_use": definition.when_to_use,
            "description": definition.description,
            "model": definition.model,
            "effort": definition.effort,
            "permission_mode": definition.permission_mode,
            "max_turns": definition.max_turns,
            "memory": definition.memory,
            "memory_scope": definition.memory_scope,
            "isolation": definition.isolation,
        }
