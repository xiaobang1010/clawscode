from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 200000
    permission_mode: str = "default"


@dataclass
class AppState:
    settings: Settings = field(default_factory=Settings)
    cwd: Path = field(default_factory=Path.cwd)
    messages: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    mcp_servers: dict = field(default_factory=dict)
