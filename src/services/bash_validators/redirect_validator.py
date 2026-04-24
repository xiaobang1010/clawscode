from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class RedirectValidator:
    name = "redirect"

    _REDIRECT = re.compile(r"[012]?>{1,2}\s*(\S+)")
    _DYNAMIC_REDIRECT = re.compile(r"[012]?>{1,2}\s*(\$|`|\$\()")

    def check(self, command: str) -> ValidationResult:
        if self._DYNAMIC_REDIRECT.search(command):
            return ValidationResult(
                is_safe=False,
                reason="动态重定向目标（变量展开），可能导致写入意外位置",
                severity="high",
            )

        for m in self._REDIRECT.finditer(command):
            target = m.group(1)
            if target.startswith("/dev/sd"):
                return ValidationResult(
                    is_safe=False,
                    reason=f"重定向到块设备: {target}",
                    severity="critical",
                )
            if target.startswith("/etc/") or target.startswith("/boot/"):
                return ValidationResult(
                    is_safe=False,
                    reason=f"重定向到系统关键目录: {target}",
                    severity="critical",
                )

        return ValidationResult(is_safe=True)
