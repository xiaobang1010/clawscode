from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class EvalLikeValidator:
    name = "eval_like"

    _EVAL_COMMANDS = re.compile(
        r"\b(eval|source|\.\s|exec|command|builtin|trap)\s",
        re.IGNORECASE,
    )

    def check(self, command: str) -> ValidationResult:
        m = self._EVAL_COMMANDS.search(command)
        if m:
            cmd = m.group(1)
            return ValidationResult(
                is_safe=False,
                reason=f"eval 类命令 '{cmd}'，可能执行任意代码",
                severity="high",
            )
        return ValidationResult(is_safe=True)
