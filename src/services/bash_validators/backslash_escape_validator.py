from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class BackslashEscapeValidator:
    name = "backslash_escape"

    _BACKSLASH_NEWLINE = re.compile(r"\\\n")
    _TRAILING_BACKSLASH = re.compile(r"(?<!\\)\\(?!n|t|r|\\\\|\"|'|\$|`|\s|$)")

    def check(self, command: str) -> ValidationResult:
        if self._BACKSLASH_NEWLINE.search(command):
            return ValidationResult(
                is_safe=False,
                reason="反斜杠换行续行符，可能导致解析差异",
                severity="medium",
            )

        if self._TRAILING_BACKSLASH.search(command):
            return ValidationResult(
                is_safe=False,
                reason="非标准反斜杠转义，可能导致解析差异",
                severity="low",
            )

        return ValidationResult(is_safe=True)
