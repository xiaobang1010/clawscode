from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class DeclarationValidator:
    name = "declaration"

    _DECLARE = re.compile(r"\bdeclare\s+(-[a-zA-Z]*[niaAlrx]*[niaAlrx])")
    _ARRAY_SUBSCRIPT = re.compile(r"\[[^\]]*\$")

    def check(self, command: str) -> ValidationResult:
        m = self._DECLARE.search(command)
        if m:
            flags = m.group(1)
            if "n" in flags:
                return ValidationResult(
                    is_safe=False,
                    reason="declare -n 名称引用可能导致间接变量攻击",
                    severity="high",
                )
            if "i" in flags or "a" in flags or "A" in flags:
                return ValidationResult(
                    is_safe=False,
                    reason=f"declare {flags} 可能导致类型强制转换或数组下标求值",
                    severity="medium",
                )

        if self._ARRAY_SUBSCRIPT.search(command):
            return ValidationResult(
                is_safe=False,
                reason="数组下标包含变量，可能导致算术求值",
                severity="medium",
            )

        return ValidationResult(is_safe=True)
