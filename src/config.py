from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from src.state import Settings
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


def load_config() -> Settings:
    _load_dotenv_files()
    global_config = load_settings(_GLOBAL_CONFIG_DIR / "settings.json")
    project_config = load_settings(_PROJECT_CONFIG_DIR / "settings.json")
    env_config = _load_env_config()

    merged = merge_settings(global_config, project_config, env_config)
    return Settings(
        api_key=merged.get("api_key", ""),
        base_url=merged.get("base_url", Settings.base_url),
        model=merged.get("model", Settings.model),
        max_tokens=int(merged.get("max_tokens", Settings.max_tokens)),
        permission_mode=merged.get("permission_mode", Settings.permission_mode),
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
