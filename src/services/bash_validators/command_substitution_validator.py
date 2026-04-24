from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class CommandSubstitutionValidator:
    name = "command_substitution"

    _DOLLAR_PAREN = re.compile(r"\$\([^)]*\)")
    _BACKTICK = re.compile(r"`[^`]*`")
    _QUOTED_CONTEXT = re.compile(r'(?:"[^"]*"|\'[^\']*\')')

    def check(self, command: str) -> ValidationResult:
        stripped = self._QUOTED_CONTEXT.sub("", command)

        for m in self._DOLLAR_PAREN.finditer(stripped):
            inner = m.group()
            if not inner.strip().startswith("$("):
                continue
            content = inner[2:-1].strip()
            if any(kw in content for kw in ("rm ", "dd ", "mkfs", ":(){", "fork")):
                return ValidationResult(
                    is_safe=False,
                    reason=f"命令替换中包含危险操作: {content[:60]}",
                    severity="critical",
                )

        if self._BACKTICK.search(stripped):
            return ValidationResult(
                is_safe=False,
                reason="反引号命令替换，建议使用 $(...) 代替",
                severity="low",
            )

        return ValidationResult(is_safe=True)
