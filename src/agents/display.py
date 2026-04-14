from __future__ import annotations

import uuid
from dataclasses import dataclass, field


AGENT_COLORS = [
    ("\033[36m", "\033[0m"),
    ("\033[35m", "\033[0m"),
    ("\033[33m", "\033[0m"),
    ("\033[34m", "\033[0m"),
    ("\033[32m", "\033[0m"),
    ("\033[31m", "\033[0m"),
    ("\033[37m", "\033[0m"),
]


@dataclass
class AgentDisplayState:
    agent_id: str
    agent_name: str
    color_start: str
    color_end: str
    depth: int = 0


class AgentDisplayManager:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDisplayState] = {}
        self._color_index: int = 0
        self._active_agents: list[str] = []

    def register_agent(self, agent_name: str) -> str:
        agent_id = str(uuid.uuid4())[:8]
        color_start, color_end = AGENT_COLORS[self._color_index % len(AGENT_COLORS)]
        self._color_index += 1

        depth = 0
        if self._active_agents:
            parent = self._agents.get(self._active_agents[-1])
            if parent:
                depth = parent.depth + 1

        state = AgentDisplayState(
            agent_id=agent_id,
            agent_name=agent_name,
            color_start=color_start,
            color_end=color_end,
            depth=depth,
        )
        self._agents[agent_id] = state
        return agent_id

    def activate(self, agent_id: str) -> None:
        if agent_id in self._agents and agent_id not in self._active_agents:
            self._active_agents.append(agent_id)

    def deactivate(self, agent_id: str) -> None:
        if agent_id in self._active_agents:
            self._active_agents.remove(agent_id)

    def format_output(self, agent_id: str, text: str) -> str:
        state = self._agents.get(agent_id)
        if not state:
            return text

        indent = "  " * state.depth
        prefix = f"{state.color_start}[{state.agent_name}]{state.color_end}"
        lines = text.split("\n")
        formatted_lines = []
        for line in lines:
            formatted_lines.append(f"{indent}{prefix} {line}")
        return "\n".join(formatted_lines)

    def format_progress(self, agent_id: str, message: str) -> str:
        state = self._agents.get(agent_id)
        if not state:
            return message

        indent = "  " * state.depth
        return f"{indent}{state.color_start}⏳ [{state.agent_name}] {message}{state.color_end}"

    def format_start(self, agent_id: str) -> str:
        state = self._agents.get(agent_id)
        if not state:
            return ""
        indent = "  " * state.depth
        return f"{indent}{state.color_start}▶ [{state.agent_name}] 开始执行{state.color_end}"

    def format_done(self, agent_id: str, summary: str = "") -> str:
        state = self._agents.get(agent_id)
        if not state:
            return ""
        indent = "  " * state.depth
        suffix = f": {summary[:100]}" if summary else ""
        return f"{indent}{state.color_start}✔ [{state.agent_name}] 完成{suffix}{state.color_end}"

    def format_error(self, agent_id: str, error: str) -> str:
        state = self._agents.get(agent_id)
        if not state:
            return f"错误: {error}"
        indent = "  " * state.depth
        return f"{indent}{state.color_start}✘ [{state.agent_name}] 错误: {error}{state.color_end}"

    def get_active_count(self) -> int:
        return len(self._active_agents)

    def get_display_state(self, agent_id: str) -> AgentDisplayState | None:
        return self._agents.get(agent_id)
