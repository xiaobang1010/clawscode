from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class ZshDangerousValidator:
    name = "zsh_dangerous"

    _DYNAMIC_DIR = re.compile(r"~\[")
    _EQUAL_EXPAND = re.compile(r"(?<!\w)=\w")
    _DANGEROUS_BUILTINS = re.compile(
        r"\b(zmodload|emulate|zpty|zcompile|zstyle)\b"
    )

    def check(self, command: str) -> ValidationResult:
        if self._DYNAMIC_DIR.search(command):
            return ValidationResult(
                is_safe=False,
                reason="zsh 动态目录 ~[name] 可能执行任意代码",
                severity="high",
            )

        if self._DANGEROUS_BUILTINS.search(command):
            return ValidationResult(
                is_safe=False,
                reason="zsh 危险内建命令",
                severity="high",
            )

        if self._EQUAL_EXPAND.search(command):
            return ValidationResult(
                is_safe=False,
                reason="zsh =cmd 等值展开可能执行命令",
                severity="medium",
            )

        return ValidationResult(is_safe=True)
