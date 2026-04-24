from __future__ import annotations

from pathlib import Path
from typing import Any

from src.hooks.types import HookDefinition, HookEvent, HookType
from src.hooks.registry import HookRegistry
from src.utils.settings import load_settings


_DEFAULT_CONFIG_PATHS = [
    Path.home() / ".clawscode" / "settings.json",
    Path.cwd() / ".clawscode" / "settings.json",
]


def load_hooks_from_settings(settings: dict[str, Any] | None = None) -> list[HookDefinition]:
    if settings is None:
        merged: dict[str, Any] = {}
        for path in _DEFAULT_CONFIG_PATHS:
            cfg = load_settings(path)
            merged.update(cfg)
        settings = merged

    hooks_config = settings.get("hooks", [])
    if not isinstance(hooks_config, list):
        return []

    definitions = []
    for cfg in hooks_config:
        if not isinstance(cfg, dict):
            continue
        try:
            hook = HookDefinition(
                name=cfg["name"],
                event=HookEvent(cfg["event"]),
                hook_type=HookType(cfg["type"]),
                command=cfg.get("command", ""),
                url=cfg.get("url", ""),
                agent_type=cfg.get("agent_type", ""),
                timeout=float(cfg.get("timeout", 30.0)),
                enabled=cfg.get("enabled", True),
                metadata=cfg.get("metadata", {}),
                if_condition=cfg.get("if", cfg.get("if_condition", "")),
                matcher=cfg.get("matcher", ""),
                once=cfg.get("once", False),
                shell_type=cfg.get("shell_type", ""),
                status_message=cfg.get("status_message", ""),
            )
            definitions.append(hook)
        except (KeyError, ValueError):
            continue

    return definitions


def load_hooks_into_registry(registry: HookRegistry, settings: dict[str, Any] | None = None) -> int:
    definitions = load_hooks_from_settings(settings)
    for hook in definitions:
        registry.register(hook)
    return len(definitions)


def get_hooks_config_schema() -> dict[str, Any]:
    return {
        "hooks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "event", "type"],
                "properties": {
                    "name": {"type": "string", "description": "Hook 名称"},
                    "event": {
                        "type": "string",
                        "enum": [e.value for e in HookEvent],
                        "description": "触发事件",
                    },
                    "type": {
                        "type": "string",
                        "enum": [t.value for t in HookType],
                        "description": "Hook 类型",
                    },
                    "command": {"type": "string", "description": "Prompt Hook 的命令"},
                    "url": {"type": "string", "description": "HTTP Hook 的 URL"},
                    "agent_type": {"type": "string", "description": "Agent Hook 的类型"},
                    "timeout": {"type": "number", "description": "超时秒数"},
                    "enabled": {"type": "boolean", "description": "是否启用"},
                    "if": {"type": "string", "description": "条件过滤（权限规则语法）"},
                    "matcher": {"type": "string", "description": "工具名匹配模式"},
                    "once": {"type": "boolean", "description": "是否为一次性 Hook"},
                    "shell_type": {"type": "string", "enum": ["bash", "powershell"], "description": "Shell 类型"},
                    "status_message": {"type": "string", "description": "自定义状态消息"},
                },
            },
        },
    }
