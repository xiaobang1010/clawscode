from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class BraceExpansionValidator:
    name = "brace_expansion"

    _BRACE = re.compile(r"\{[^}]*,[^}]*\}")
    _QUOTED = re.compile(r'(?:"[^"]*"|\'[^\']*\')')

    def check(self, command: str) -> ValidationResult:
        stripped = self._QUOTED.sub("", command)
        if self._BRACE.search(stripped):
            return ValidationResult(
                is_safe=False,
                reason="花括号展开可能导致参数数量膨胀或与引号混淆",
                severity="low",
            )
        return ValidationResult(is_safe=True)
