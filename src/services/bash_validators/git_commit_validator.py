from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class GitCommitValidator:
    name = "git_commit"

    _GIT_COMMIT = re.compile(r"\bgit\s+commit\b")
    _DANGEROUS_FLAGS = re.compile(
        r"\bgit\s+commit\s+.*(--author|--date|--exec)\b"
    )

    def check(self, command: str) -> ValidationResult:
        if not self._GIT_COMMIT.search(command):
            return ValidationResult(is_safe=True)

        if self._DANGEROUS_FLAGS.search(command):
            return ValidationResult(
                is_safe=False,
                reason="git commit 包含篡改标志 (--author/--date/--exec)",
                severity="high",
            )

        return ValidationResult(is_safe=True)
