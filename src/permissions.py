from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.state import Settings
from src.tool import PermissionResult, Tool


class PermissionChecker:
    def __init__(self, settings: Settings):
        self.deny_rules: list[str] = getattr(settings, "deny_rules", [])
        self.ask_rules: list[str] = getattr(settings, "ask_rules", [])
        self.allow_rules: list[str] = getattr(settings, "allow_rules", [])

    async def check(self, tool: Tool, input: BaseModel, context: Any) -> PermissionResult:
        result = self._check_deny(tool, input)
        if result is not None:
            return result

        result = self._check_ask(tool, input)
        if result is not None:
            return result

        perm = await tool.check_permissions(input, context)
        if perm is not None:
            return perm

        result = self._check_allow(tool, input)
        if result is not None:
            return result

        return PermissionResult.ASK

    def _check_deny(self, tool: Tool, input: BaseModel) -> PermissionResult | None:
        for rule in self.deny_rules:
            if self._matches(rule, tool, input):
                return PermissionResult.DENY
        return None

    def _check_ask(self, tool: Tool, input: BaseModel) -> PermissionResult | None:
        for rule in self.ask_rules:
            if self._matches(rule, tool, input):
                return PermissionResult.ASK
        return None

    def _check_allow(self, tool: Tool, input: BaseModel) -> PermissionResult | None:
        for rule in self.allow_rules:
            if self._matches(rule, tool, input):
                return PermissionResult.ALLOW
        return None

    def _matches(self, rule: str, tool: Tool, input: BaseModel) -> bool:
        return rule == tool.name or rule == f"{tool.name}:*"
