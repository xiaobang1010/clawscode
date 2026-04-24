from __future__ import annotations

import re

from src.services.bash_validators import BashValidator, ValidationResult


class WrapperCommandValidator:
    name = "wrapper_command"

    _WRAPPERS = re.compile(
        r"^\s*(time|nohup|timeout|nice|ionice|env|stdbuf|chroot|setsid|setarch|unshare|strace|ltrace)\s+",
        re.IGNORECASE,
    )
    _KNOWN_WRAPPERS = {"time", "nohup", "timeout", "nice", "ionice", "env", "stdbuf",
                       "chroot", "setsid", "setarch", "unshare", "strace", "ltrace"}

    def check(self, command: str) -> ValidationResult:
        stripped = command.strip()
        unwrapped = self._unwrap(stripped)
        if unwrapped != stripped:
            from src.services.bash_classifier import classify_bash_command
            inner_class = classify_bash_command(unwrapped)
            if inner_class == "dangerous":
                return ValidationResult(
                    is_safe=False,
                    reason=f"包装命令内的实际命令被判定为危险: {unwrapped[:60]}",
                    severity="high",
                )
        return ValidationResult(is_safe=True)

    def _unwrap(self, command: str) -> str:
        while True:
            m = self._WRAPPERS.match(command)
            if not m:
                break
            command = command[m.end():]
            parts = command.split(None, 1)
            if not parts:
                break
            if m.group(1).lower() in ("timeout", "nice", "ionice", "env", "stdbuf"):
                if parts[0].startswith("-"):
                    command = parts[1] if len(parts) > 1 else ""
                    continue
            command = parts[-1] if len(parts) > 1 else parts[0]
        return command.strip()
