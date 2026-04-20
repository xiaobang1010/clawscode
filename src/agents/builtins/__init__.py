from __future__ import annotations

from src.agents.agent_definition import AgentDefinition
from src.agents.builtins.explore import create_explore_agent
from src.agents.builtins.general import create_general_agent
from src.agents.builtins.plan import create_plan_agent
from src.agents.builtins.verification import create_verification_agent


def get_builtin_agents() -> list[AgentDefinition]:
    return [
        create_general_agent(),
        create_explore_agent(),
        create_plan_agent(),
        create_verification_agent(),
    ]


def register_builtins(loader_or_registry) -> None:
    from src.agents.loader import AgentLoader

    if isinstance(loader_or_registry, AgentLoader):
        for agent in get_builtin_agents():
            loader_or_registry.register(agent)
    elif isinstance(loader_or_registry, dict):
        for agent in get_builtin_agents():
            loader_or_registry[agent.name] = agent
