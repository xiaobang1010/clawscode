from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class JqSystemValidator:
    name = "jq_system"

    _SYSTEM_CALL = re.compile(r"\bsystem\s*\(")
    _DANGEROUS_FLAGS = re.compile(r"\bjq\s+.*(-f|--from-file)\s")
    _LOAD_FLAG = re.compile(r"\bjq\s+.*-L\s")

    def check(self, command: str) -> ValidationResult:
        if "jq" not in command:
            return ValidationResult(is_safe=True)

        if self._SYSTEM_CALL.search(command):
            return ValidationResult(
                is_safe=False,
                reason="jq system() 调用可执行任意命令",
                severity="critical",
            )

        if self._DANGEROUS_FLAGS.search(command):
            return ValidationResult(
                is_safe=False,
                reason="jq -f 标志可从文件加载并执行代码",
                severity="high",
            )

        if self._LOAD_FLAG.search(command):
            return ValidationResult(
                is_safe=False,
                reason="jq -L 标志可加载模块路径",
                severity="medium",
            )

        return ValidationResult(is_safe=True)
