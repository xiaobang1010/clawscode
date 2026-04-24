from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class IFSInjectionValidator:
    name = "ifs_injection"

    _IFS_ASSIGN = re.compile(r"\bIFS\s*=")
    _BARE_VAR = re.compile(r"(?<!\w)\$\{?[a-zA-Z_]\w*\}?(?!\w)")

    def check(self, command: str) -> ValidationResult:
        if self._IFS_ASSIGN.search(command):
            return ValidationResult(
                is_safe=False,
                reason="IFS 注入风险: IFS 变量赋值可能改变分词行为",
                severity="high",
            )

        if self._BARE_VAR.search(command):
            return ValidationResult(
                is_safe=False,
                reason="IFS 注入风险: 裸变量展开可能受 IFS 影响",
                severity="medium",
            )

        return ValidationResult(is_safe=True)
