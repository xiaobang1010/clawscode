from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class UnicodeWhitespaceValidator:
    name = "unicode_whitespace"

    _PATTERN = re.compile(
        r"[\u00a0\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\ufeff]"
    )

    def check(self, command: str) -> ValidationResult:
        match = self._PATTERN.search(command)
        if match:
            ch = match.group()
            return ValidationResult(
                is_safe=False,
                reason=f"Unicode 空白可能导致解析差异: U+{ord(ch):04X}",
                severity="medium",
            )
        return ValidationResult(is_safe=True)
