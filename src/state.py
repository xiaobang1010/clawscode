from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SessionState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    REQUIRES_ACTION = "requires_action"


@dataclass
class CostTracker:
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    api_calls: int = 0
    total_duration_ms: float = 0.0

    def add(self, input_tokens: int = 0, output_tokens: int = 0, cost: float = 0.0, duration_ms: float = 0.0) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_cost += cost
        self.api_calls += 1
        self.total_duration_ms += duration_ms

    def format_summary(self) -> str:
        return f"Tokens: {self.input_tokens}+{self.output_tokens} | Cost: ${self.total_cost:.4f} | API: {self.api_calls} calls | Time: {self.total_duration_ms:.0f}ms"


@dataclass
class TodoItem:
    id: str
    content: str
    status: str = "pending"
    priority: str = "medium"


@dataclass
class Settings:
    api_key: str = ""
    base_url: str = "https://api-inference.modelscope.cn/v1"
    model: str = "ZhipuAI/GLM-5"
    max_tokens: int = 128000
    permission_mode: str = "default"
    deny_rules: list[str] = field(default_factory=list)
    ask_rules: list[str] = field(default_factory=list)
    allow_rules: list[str] = field(default_factory=list)


@dataclass
class AppState:
    settings: Settings = field(default_factory=Settings)
    cwd: Path = field(default_factory=Path.cwd)
    messages: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    mcp_servers: dict = field(default_factory=dict)
    checkpoint_count: int = 0
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_title: str = ""
    session_state: SessionState = SessionState.IDLE
    cost_tracker: CostTracker = field(default_factory=CostTracker)
    file_history: list[dict] = field(default_factory=list)
    todo_list: list[TodoItem] = field(default_factory=list)
    agent_definitions: list[dict] = field(default_factory=list)
    read_files: set[str] = field(default_factory=set)
    permission_checker: Any = None
