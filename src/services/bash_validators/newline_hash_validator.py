from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class NewlineHashValidator:
    name = "newline_hash"

    _NEWLINE_HASH = re.compile(r"\\n\s*#")
    _ENV_NEWLINE_HASH = re.compile(r"=\s*.*\\n\s*#")

    def check(self, command: str) -> ValidationResult:
        if self._NEWLINE_HASH.search(command):
            return ValidationResult(
                is_safe=False,
                reason="参数中包含 \\n# 模式，可能导致注释注入",
                severity="medium",
            )

        if self._ENV_NEWLINE_HASH.search(command):
            return ValidationResult(
                is_safe=False,
                reason="环境变量值中包含 \\n# 模式，可能导致注释注入",
                severity="high",
            )

        return ValidationResult(is_safe=True)
