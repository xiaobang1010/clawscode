from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class EmptyCommandValidator:
    name = "empty_command"

    _EMPTY = re.compile(r"^\s*$")
    _PLACEHOLDER = re.compile(r"^\s*(true|false|:|exit\s*\d*|nop)\s*$")

    def check(self, command: str) -> ValidationResult:
        if self._EMPTY.match(command):
            return ValidationResult(
                is_safe=False,
                reason="空命令名",
                severity="low",
            )

        stripped = command.strip()
        parts = stripped.split()
        if parts:
            base = parts[0]
            if base.startswith("$(") or base.startswith("`"):
                return ValidationResult(
                    is_safe=False,
                    reason="占位符命令名，实际为命令替换",
                    severity="medium",
                )

        return ValidationResult(is_safe=True)
