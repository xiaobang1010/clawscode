from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class ControlCharValidator:
    name = "control_char"

    _PATTERN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

    def check(self, command: str) -> ValidationResult:
        match = self._PATTERN.search(command)
        if match:
            ch = match.group()
            return ValidationResult(
                is_safe=False,
                reason=f"控制字符可能导致解析差异: 0x{ord(ch):02x}",
                severity="high",
            )
        return ValidationResult(is_safe=True)
