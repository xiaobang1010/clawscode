from __future__ import annotations

import fnmatch
from enum import Enum
from typing import Any

from pydantic import BaseModel

from src.state import Settings
from src.tool import PermissionResult, Tool


class PermissionMode(str, Enum):
    DEFAULT = "default"
    PLAN = "plan"
    BYPASS = "bypass"
    AUTO = "auto"


PLAN_READONLY_TOOLS = {"Glob", "FileRead", "Grep", "GlobTool", "ToolSearch", "SleepTool", "ExitPlanMode"}

DEFAULT_DENY_RULES = [
    "Bash:rm -rf /*",
    "Bash:mkfs*",
    "Bash:dd if=*",
    "Bash:format *",
    "Bash:del /s *",
]

DEFAULT_ASK_RULES = [
    "Bash:*install *",
    "Bash:*pip install*",
    "Bash:*npm install*",
    "Bash:*uv add*",
    "Bash:*rm *",
    "Bash:*rmdir*",
    "Bash:*del *",
]

DEFAULT_ALLOW_RULES = [
    "Glob:*",
    "FileRead:*",
    "Grep:*",
    "Bash:*",
    "FileEdit:*",
    "FileWrite:*",
]

_killswitch_active = False


def activate_killswitch() -> None:
    global _killswitch_active
    _killswitch_active = True


def is_killswitch_active() -> bool:
    return _killswitch_active


class PermissionChecker:
    def __init__(self, settings: Settings, mode: PermissionMode | None = None):
        if mode is not None:
            self._mode = mode
        else:
            try:
                self._mode = PermissionMode(settings.permission_mode)
            except ValueError:
                self._mode = PermissionMode.DEFAULT
        self.deny_rules: list[str] = list(DEFAULT_DENY_RULES) + list(settings.deny_rules)
        self.ask_rules: list[str] = list(DEFAULT_ASK_RULES) + list(settings.ask_rules)
        self.allow_rules: list[str] = list(settings.allow_rules)

        for rule in DEFAULT_ALLOW_RULES:
            if rule not in self.allow_rules:
                self.allow_rules.append(rule)

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    def set_mode(self, mode: PermissionMode) -> None:
        self._mode = mode

    async def check(self, tool: Tool, input: BaseModel, context: Any) -> PermissionResult:
        if self._mode == PermissionMode.BYPASS:
            if is_killswitch_active():
                return PermissionResult.DENY
            return PermissionResult.ALLOW

        if self._mode == PermissionMode.PLAN:
            if tool.name not in PLAN_READONLY_TOOLS:
                return PermissionResult.DENY
            return PermissionResult.ALLOW

        result = self._check_deny(tool, input)
        if result is not None:
            return result

        result = self._check_ask(tool, input)
        if result is not None:
            return result

        result = self._check_allow(tool, input)
        if result is not None:
            return result

        perm = await tool.check_permissions(input, context)
        if perm is not None:
            return perm

        if self._mode == PermissionMode.AUTO:
            return self._auto_classify(tool, input)

        return PermissionResult.ALLOW

    def add_allow_rule(self, rule: str) -> None:
        if rule not in self.allow_rules:
            self.allow_rules.append(rule)

    def remove_allow_rule(self, rule: str) -> bool:
        if rule in self.allow_rules:
            self.allow_rules.remove(rule)
            return True
        return False

    def _auto_classify(self, tool: Tool, input: BaseModel) -> PermissionResult:
        try:
            from src.services.bash_classifier import classify_bash_command
            from src.services.dangerous_patterns import is_dangerous

            if tool.name == "Bash":
                command = getattr(input, "command", "") or str(input)
                if is_dangerous(command):
                    return PermissionResult.ASK
                classification = classify_bash_command(command)
                if classification == "safe":
                    return PermissionResult.ALLOW
                elif classification == "dangerous":
                    return PermissionResult.DENY
                return PermissionResult.ASK
        except ImportError:
            pass

        if getattr(tool, "is_readonly", False):
            return PermissionResult.ALLOW

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
