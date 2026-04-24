from __future__ import annotations

from src.hooks.types import HookDefinition, HookEvent, HookType


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[str, HookDefinition] = {}

    def register(self, hook: HookDefinition) -> None:
        self._hooks[hook.name] = hook

    def unregister(self, name: str) -> None:
        self._hooks.pop(name, None)

    def get(self, name: str) -> HookDefinition | None:
        return self._hooks.get(name)

    def find_by_event(self, event: HookEvent, tool_name: str = "") -> list[HookDefinition]:
        hooks = [h for h in self._hooks.values() if h.event == event and h.enabled]
        if tool_name:
            hooks = [
                h for h in hooks
                if not h.matcher or h.matcher == tool_name or _fnmatch_simple(tool_name, h.matcher)
            ]
        return hooks

    def find_all_enabled(self) -> list[HookDefinition]:
        return [h for h in self._hooks.values() if h.enabled]

    def list_all(self) -> list[HookDefinition]:
        return list(self._hooks.values())

    def clear(self) -> None:
        self._hooks.clear()

    def enable(self, name: str) -> None:
        hook = self._hooks.get(name)
        if hook is not None:
            hook.enabled = True

    def disable(self, name: str) -> None:
        hook = self._hooks.get(name)
        if hook is not None:
            hook.enabled = False

    def load_from_config(self, configs: list[dict]) -> None:
        for cfg in configs:
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
                self.register(hook)
            except (KeyError, ValueError):
                continue


def _fnmatch_simple(name: str, pattern: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(name, pattern)
