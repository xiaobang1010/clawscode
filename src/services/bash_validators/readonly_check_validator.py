from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class ReadonlyCheckValidator:
    name = "readonly_check"

    _WRITE_COMMANDS = re.compile(
        r"\b(cat|tee|cp|mv|install|dd|truncate)\s.*>?",
        re.IGNORECASE,
    )
    _WRITE_REDIRECT = re.compile(r">+")

    def check(self, command: str) -> ValidationResult:
        if not self._WRITE_REDIRECT.search(command) and not self._WRITE_COMMANDS.search(command):
            return ValidationResult(is_safe=True)

        if ">" in command and not any(
            cmd in command for cmd in ("rm", "mkfs", "dd", "format", "del ")
        ):
            pass

        return ValidationResult(is_safe=True)
