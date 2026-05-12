from __future__ import annotations

from typing import Any

from src.hooks.config import load_hooks_into_registry
from src.hooks.executor import HookExecutor
from src.hooks.registry import HookRegistry
from src.boot.state import Settings


def build_hook_snapshot(settings: Settings) -> HookExecutor | None:
    if not settings.hooks.enabled:
        return None
    if not settings.hooks.hooks:
        return None

    settings_dict: dict[str, Any] = {"hooks": settings.hooks.hooks}
    try:
        registry = HookRegistry()
        count = load_hooks_into_registry(registry, settings=settings_dict)
        if count > 0:
            registry.freeze()
            return HookExecutor(registry)
    except Exception:
        pass
    return None
