from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class VariableExpansionValidator:
    name = "variable_expansion"

    _BARE_VAR = re.compile(r"(?<!\w)\$[a-zA-Z_]\w*(?!\w)")
    _GLOB_CHARS = re.compile(r"[*?\[\]]")

    def check(self, command: str) -> ValidationResult:
        issues = []

        bare_vars = self._BARE_VAR.findall(command)
        if bare_vars:
            remaining = self._BARE_VAR.sub("", command)
            if self._GLOB_CHARS.search(remaining):
                issues.append("裸变量展开中可能包含 glob 字符")

        for var in bare_vars:
            if re.search(rf"(?<!\w){re.escape(var)}(?=\s|$)", command):
                issues.append(f"空值裸变量 '{var}' 可能导致参数丢失")

        if issues:
            return ValidationResult(
                is_safe=False,
                reason="; ".join(issues),
                severity="medium",
            )

        return ValidationResult(is_safe=True)
