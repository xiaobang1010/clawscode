from __future__ import annotations

from pathlib import Path


RUNTIME_DATA_DIR_NAME = ".clawscode"

CONFIG_DIR = Path.cwd() / "config"
RUNTIME_DATA_DIR = Path.cwd() / RUNTIME_DATA_DIR_NAME
GLOBAL_RUNTIME_DIR = Path.home() / RUNTIME_DATA_DIR_NAME


def get_config_dir() -> Path:
    return CONFIG_DIR


def get_runtime_data_dir() -> Path:
    return RUNTIME_DATA_DIR


def get_global_runtime_dir() -> Path:
    return GLOBAL_RUNTIME_DIR


def get_config_file() -> Path:
    return CONFIG_DIR / "settings.json"


def get_history_dir(cwd: Path) -> Path:
    return cwd / RUNTIME_DATA_DIR_NAME


def get_mcp_token_path() -> Path:
    return GLOBAL_RUNTIME_DIR / "mcp_oauth_tokens.json"


def get_sidechain_dir(base_dir: Path | None = None) -> Path:
    return (base_dir or GLOBAL_RUNTIME_DIR) / "sidechains"


def get_tool_result_dir() -> Path:
    return GLOBAL_RUNTIME_DIR


def get_memdir(cwd: Path, memdir: str = "") -> Path:
    if memdir:
        return cwd / memdir
    return cwd / RUNTIME_DATA_DIR_NAME / "memdir"


def get_global_memdir() -> Path:
    return GLOBAL_RUNTIME_DIR / "memdir"


def get_kairos_dir(cwd: Path) -> Path:
    return cwd / RUNTIME_DATA_DIR_NAME / "kairos"
