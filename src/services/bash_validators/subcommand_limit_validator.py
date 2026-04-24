from __future__ import annotations

from src.services.bash_validators import BashValidator, ValidationResult


class SubcommandLimitValidator:
    name = "subcommand_limit"

    MAX_SUBCOMMANDS = 50

    def check(self, command: str) -> ValidationResult:
        separators = ("&&", "||", ";", "|", "&")
        parts = [command]
        for sep in separators:
            new_parts = []
            for p in parts:
                new_parts.extend(p.split(sep))
            parts = new_parts

        subcommands = [p.strip() for p in parts if p.strip()]
        if len(subcommands) > self.MAX_SUBCOMMANDS:
            return ValidationResult(
                is_safe=False,
                reason=f"子命令过多 ({len(subcommands)})，可能为 ReDoS 攻击",
                severity="critical",
            )
        return ValidationResult(is_safe=True)
