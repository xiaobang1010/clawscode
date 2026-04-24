from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class ProcEnvironValidator:
    name = "proc_environ"

    _PATTERN = re.compile(r"/proc/\S*/environ")

    def check(self, command: str) -> ValidationResult:
        if self._PATTERN.search(command):
            return ValidationResult(
                is_safe=False,
                reason="访问 /proc/*/environ 可能泄露进程环境变量（含密钥）",
                severity="critical",
            )
        return ValidationResult(is_safe=True)
