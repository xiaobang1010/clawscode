from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from src.state import (
    Settings,
    HooksConfig,
    AgentsConfig,
    SkillsConfig,
    PluginsConfig,
    CostConfig,
    SessionConfig,
    MemoryConfig,
)
from src.utils.settings import load_settings, merge_settings

_GLOBAL_CONFIG_DIR = Path.home() / ".clawscode"
_PROJECT_CONFIG_DIR = Path.cwd() / ".clawscode"

_ENV_KEY_MAP = {
    "CLAWSCODE_API_KEY": "api_key",
    "CLAWSCODE_BASE_URL": "base_url",
    "CLAWSCODE_MODEL": "model",
    "CLAWSCODE_MAX_TOKENS": "max_tokens",
    "CLAWSCODE_PERMISSION_MODE": "permission_mode",
    "API_KEY": "api_key",
    "MODEL": "model",
}


def load_config() -> tuple[Settings, dict[str, dict]]:
    _load_dotenv_files()
    global_config = load_settings(_GLOBAL_CONFIG_DIR / "settings.json")
    project_config = load_settings(_PROJECT_CONFIG_DIR / "settings.json")
    env_config = _load_env_config()

    merged = merge_settings(global_config, project_config, env_config)
    mcp_servers = merged.get("mcp_servers", {})
    settings = Settings(
        api_key=merged.get("api_key", ""),
        base_url=merged.get("base_url", Settings.base_url),
        model=merged.get("model", Settings.model),
        max_tokens=int(merged.get("max_tokens", Settings.max_tokens)),
        permission_mode=merged.get("permission_mode", Settings.permission_mode),
        deny_rules=merged.get("deny_rules", []),
        ask_rules=merged.get("ask_rules", []),
        allow_rules=merged.get("allow_rules", []),
        hooks=_load_hooks_config(merged),
        agents=_load_agents_config(merged),
        skills=_load_skills_config(merged),
        plugins=_load_plugins_config(merged),
        cost=_load_cost_config(merged),
        session=_load_session_config(merged),
        memory=_load_memory_config(merged),
    )
    return (settings, mcp_servers)


def _load_hooks_config(merged: dict) -> HooksConfig:
    hooks_section = merged.get("hooks", {})
    if isinstance(hooks_section, list):
        return HooksConfig(hooks=hooks_section)
    return HooksConfig(
        enabled=hooks_section.get("enabled", True),
        hooks=hooks_section.get("hooks", []),
    )


def _load_agents_config(merged: dict) -> AgentsConfig:
    agents_section = merged.get("agents", {})
    if isinstance(agents_section, list):
        return AgentsConfig(definitions=agents_section)
    return AgentsConfig(
        search_paths=agents_section.get("search_paths", []),
        definitions=agents_section.get("definitions", []),
    )


def _load_skills_config(merged: dict) -> SkillsConfig:
    skills_section = merged.get("skills", {})
    return SkillsConfig(
        search_paths=skills_section.get("search_paths", []),
        bundled_enabled=skills_section.get("bundled_enabled", True),
    )


def _load_plugins_config(merged: dict) -> PluginsConfig:
    plugins_section = merged.get("plugins", {})
    return PluginsConfig(
        search_paths=plugins_section.get("search_paths", []),
        enabled=plugins_section.get("enabled", []),
        disabled=plugins_section.get("disabled", []),
    )


def _load_cost_config(merged: dict) -> CostConfig:
    cost_section = merged.get("cost", {})
    return CostConfig(
        pricing=cost_section.get("pricing", {}),
    )


def _load_session_config(merged: dict) -> SessionConfig:
    session_section = merged.get("session", {})
    return SessionConfig(
        storage_path=session_section.get("storage_path", ""),
        auto_save_interval=int(session_section.get("auto_save_interval", 60)),
    )


def _load_memory_config(merged: dict) -> MemoryConfig:
    memory_section = merged.get("memory", {})
    return MemoryConfig(
        memdir=memory_section.get("memdir", ""),
        search_nested=memory_section.get("search_nested", True),
    )


def _load_dotenv_files() -> None:
    project_env = Path.cwd() / ".env"
    if project_env.exists():
        load_dotenv(project_env, override=False)


def _load_env_config() -> dict[str, str]:
    result: dict[str, str] = {}
    for env_key, setting_key in _ENV_KEY_MAP.items():
        value = os.environ.get(env_key)
        if value is not None:
            result[setting_key] = value
    return result
