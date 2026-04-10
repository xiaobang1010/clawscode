from __future__ import annotations

import fnmatch
from typing import Any

from pydantic import BaseModel

from src.state import Settings
from src.tool import PermissionResult, Tool

DEFAULT_DENY_RULES = [
    "Bash:rm -rf /*",
    "Bash:rm -rf /*",
    "Bash:mkfs*",
    "Bash:dd if=*",
    "Bash:format *",
    "Bash:del /s *",
]


class PermissionChecker:
    def __init__(self, settings: Settings):
        self.deny_rules: list[str] = list(DEFAULT_DENY_RULES) + list(settings.deny_rules)
        self.ask_rules: list[str] = list(settings.ask_rules)
        self.allow_rules: list[str] = list(settings.allow_rules)

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

    def add_allow_rule(self, rule: str) -> None:
        if rule not in self.allow_rules:
            self.allow_rules.append(rule)

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
        if ":" not in rule:
            return rule == tool.name or fnmatch.fnmatch(tool.name, rule)

        rule_tool, _, rule_pattern = rule.partition(":")
        if not fnmatch.fnmatch(tool.name, rule_tool) and rule_tool != tool.name:
            return False

        if rule_pattern == "*":
            return True

        input_str = str(input)
        if hasattr(input, "model_dump"):
            input_str = str(input.model_dump())
        return fnmatch.fnmatch(input_str, rule_pattern) or any(
            fnmatch.fnmatch(str(v), rule_pattern)
            for v in (input.model_dump() if hasattr(input, "model_dump") else {}).values()
        )
