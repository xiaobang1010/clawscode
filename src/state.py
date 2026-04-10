from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
