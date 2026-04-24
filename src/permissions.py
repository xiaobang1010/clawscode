from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
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
    ACCEPT_EDITS = "acceptEdits"
    DONT_ASK = "dontAsk"
    BUBBLE = "bubble"


class PermissionRuleSource(str, Enum):
    USER_SETTINGS = "userSettings"
    PROJECT_SETTINGS = "projectSettings"
    SESSION = "session"
    CLI_ARG = "cliArg"
    DEFAULT = "default"


class PermissionDecisionReason(str, Enum):
    RULE = "rule"
    MODE = "mode"
    HOOK = "hook"
    CLASSIFIER = "classifier"
    SAFETY_CHECK = "safetyCheck"
    SANDBOX_OVERRIDE = "sandboxOverride"
    WORKING_DIR = "workingDir"
    DEFAULT = "default"


@dataclass
class PermissionDecision:
    result: PermissionResult
    reason: PermissionDecisionReason = PermissionDecisionReason.DEFAULT
    matched_rule: str | None = None
    rule_source: PermissionRuleSource | None = None

    def to_permission_result(self) -> PermissionResult:
        return self.result


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

EDIT_TOOLS = {"FileEdit", "FileWrite", "NotebookEdit"}

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

        self.deny_rules: list[tuple[str, PermissionRuleSource]] = [
            (r, PermissionRuleSource.DEFAULT) for r in DEFAULT_DENY_RULES
        ] + [
            (r, PermissionRuleSource.USER_SETTINGS) for r in settings.deny_rules
        ]

        self.ask_rules: list[tuple[str, PermissionRuleSource]] = [
            (r, PermissionRuleSource.DEFAULT) for r in DEFAULT_ASK_RULES
        ] + [
            (r, PermissionRuleSource.USER_SETTINGS) for r in settings.ask_rules
        ]

        self.allow_rules: list[tuple[str, PermissionRuleSource]] = [
            (r, PermissionRuleSource.USER_SETTINGS) for r in settings.allow_rules
        ]

        for rule in DEFAULT_ALLOW_RULES:
            if rule not in [r for r, _ in self.allow_rules]:
                self.allow_rules.append((rule, PermissionRuleSource.DEFAULT))

        self._additional_working_directories: list[str] = list(
            getattr(settings, "additional_working_directories", [])
        )

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    @property
    def additional_working_directories(self) -> list[str]:
        return self._additional_working_directories

    def set_mode(self, mode: PermissionMode) -> None:
        self._mode = mode

    async def check(self, tool: Tool, input: BaseModel, context: Any) -> PermissionResult:
        decision = self.check_detailed(tool, input, context)
        return decision.to_permission_result()

    def check_detailed(self, tool: Tool, input: BaseModel, context: Any) -> PermissionDecision:
        if self._mode == PermissionMode.BYPASS:
            if is_killswitch_active():
                return PermissionDecision(
                    result=PermissionResult.DENY,
                    reason=PermissionDecisionReason.SAFETY_CHECK,
                )
            return PermissionDecision(
                result=PermissionResult.ALLOW,
                reason=PermissionDecisionReason.MODE,
            )

        if self._mode == PermissionMode.PLAN:
            if tool.name not in PLAN_READONLY_TOOLS:
                return PermissionDecision(
                    result=PermissionResult.DENY,
                    reason=PermissionDecisionReason.MODE,
                )
            return PermissionDecision(
                result=PermissionResult.ALLOW,
                reason=PermissionDecisionReason.MODE,
            )

        if self._mode == PermissionMode.ACCEPT_EDITS:
            if tool.name in EDIT_TOOLS:
                return PermissionDecision(
                    result=PermissionResult.ALLOW,
                    reason=PermissionDecisionReason.MODE,
                )

        if self._mode == PermissionMode.DONT_ASK:
            deny_result = self._check_deny_detailed(tool, input)
            if deny_result:
                return deny_result

            allow_result = self._check_allow_detailed(tool, input)
            if allow_result:
                return allow_result

            return PermissionDecision(
                result=PermissionResult.DENY,
                reason=PermissionDecisionReason.DEFAULT,
            )

        if self._mode == PermissionMode.BUBBLE:
            parent = getattr(context, "parent_agent", None)
            if parent is not None:
                return PermissionDecision(
                    result=PermissionResult.ASK,
                    reason=PermissionDecisionReason.MODE,
                )

        result = self._check_deny_detailed(tool, input)
        if result:
            return result

        result = self._check_ask_detailed(tool, input)
        if result:
            return result

        result = self._check_allow_detailed(tool, input)
        if result:
            return result

        return PermissionDecision(
            result=PermissionResult.ALLOW,
            reason=PermissionDecisionReason.DEFAULT,
        )

    def add_allow_rule(self, rule: str, source: PermissionRuleSource = PermissionRuleSource.SESSION) -> None:
        if rule not in [r for r, _ in self.allow_rules]:
            self.allow_rules.append((rule, source))

    def remove_allow_rule(self, rule: str) -> bool:
        for i, (r, s) in enumerate(self.allow_rules):
            if r == rule:
                self.allow_rules.pop(i)
                return True
        return False

    def _auto_classify(self, tool: Tool, input: BaseModel) -> PermissionDecision:
        try:
            from src.services.bash_classifier import classify_bash_command
            from src.services.dangerous_patterns import is_dangerous

            if tool.name == "Bash":
                command = getattr(input, "command", "") or str(input)
                if is_dangerous(command):
                    return PermissionDecision(
                        result=PermissionResult.ASK,
                        reason=PermissionDecisionReason.CLASSIFIER,
                    )
                classification = classify_bash_command(command)
                if classification == "safe":
                    return PermissionDecision(
                        result=PermissionResult.ALLOW,
                        reason=PermissionDecisionReason.CLASSIFIER,
                    )
                elif classification == "dangerous":
                    return PermissionDecision(
                        result=PermissionResult.DENY,
                        reason=PermissionDecisionReason.CLASSIFIER,
                    )
                return PermissionDecision(
                    result=PermissionResult.ASK,
                    reason=PermissionDecisionReason.CLASSIFIER,
                )
        except ImportError:
            pass

        if getattr(tool, "is_readonly", False):
            return PermissionDecision(
                result=PermissionResult.ALLOW,
                reason=PermissionDecisionReason.CLASSIFIER,
            )

        return PermissionDecision(
            result=PermissionResult.ASK,
            reason=PermissionDecisionReason.DEFAULT,
        )

    def _check_deny_detailed(self, tool: Tool, input: BaseModel) -> PermissionDecision | None:
        for rule, source in self.deny_rules:
            if self._matches(rule, tool, input):
                return PermissionDecision(
                    result=PermissionResult.DENY,
                    reason=PermissionDecisionReason.RULE,
                    matched_rule=rule,
                    rule_source=source,
                )
        return None

    def _check_ask_detailed(self, tool: Tool, input: BaseModel) -> PermissionDecision | None:
        for rule, source in self.ask_rules:
            if self._matches(rule, tool, input):
                return PermissionDecision(
                    result=PermissionResult.ASK,
                    reason=PermissionDecisionReason.RULE,
                    matched_rule=rule,
                    rule_source=source,
                )
        return None

    def _check_allow_detailed(self, tool: Tool, input: BaseModel) -> PermissionDecision | None:
        for rule, source in self.allow_rules:
            if self._matches(rule, tool, input):
                return PermissionDecision(
                    result=PermissionResult.ALLOW,
                    reason=PermissionDecisionReason.RULE,
                    matched_rule=rule,
                    rule_source=source,
                )
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

    def is_path_in_working_dirs(self, path: str) -> bool:
        from pathlib import Path
        try:
            p = Path(path).resolve()
            cwd = Path(getattr(self, "_cwd", Path.cwd())).resolve()
            if str(p).startswith(str(cwd)):
                return True
            for wd in self._additional_working_directories:
                wd_path = Path(wd).resolve()
                if str(p).startswith(str(wd_path)):
                    return True
        except (OSError, ValueError):
            pass
        return False

    async def await_automated_checks_before_dialog(self, tool: Tool, input: BaseModel, context: Any) -> PermissionDecision | None:
        deny = self._check_deny_detailed(tool, input)
        if deny:
            return deny

        allow = self._check_allow_detailed(tool, input)
        if allow:
            return allow

        return None
