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
class TodoItem:
    id: str
    content: str
    status: str = "pending"
    priority: str = "medium"


@dataclass
class HooksConfig:
    enabled: bool = True
    hooks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentsConfig:
    search_paths: list[str] = field(default_factory=list)
    definitions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SkillsConfig:
    search_paths: list[str] = field(default_factory=list)
    bundled_enabled: bool = True


@dataclass
class PluginsConfig:
    search_paths: list[str] = field(default_factory=list)
    enabled: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)


@dataclass
class CostConfig:
    pricing: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class SessionConfig:
    storage_path: str = ""
    auto_save_interval: int = 60


@dataclass
class MemoryConfig:
    memdir: str = ""
    search_nested: bool = True


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
    hooks: HooksConfig = field(default_factory=HooksConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)

    @property
    def effective_max_tokens(self) -> int:
        from src.services.token_budget import infer_context_window
        inferred = infer_context_window(self.model)
        if self.max_tokens != 128000:
            return self.max_tokens
        return inferred


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
    cost_tracker_service: Any = None
    file_history: list[dict] = field(default_factory=list)
    todo_list: list[TodoItem] = field(default_factory=list)
    agent_definitions: list[dict] = field(default_factory=list)
    read_files: set[str] = field(default_factory=set)
    permission_checker: Any = None
