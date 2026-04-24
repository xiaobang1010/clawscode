from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ValidationResult:
    is_safe: bool
    reason: str = ""
    severity: str = "medium"

    def __post_init__(self):
        valid = ("low", "medium", "high", "critical")
        if self.severity not in valid:
            self.severity = "medium"


@runtime_checkable
class BashValidator(Protocol):
    name: str

    def check(self, command: str) -> ValidationResult: ...


ALL_VALIDATORS: list[BashValidator] = []


def register_validator(validator: BashValidator) -> None:
    ALL_VALIDATORS.append(validator)


def run_all_validators(command: str) -> list[ValidationResult]:
    results = []
    for v in ALL_VALIDATORS:
        result = v.check(command)
        if not result.is_safe:
            results.append(result)
    return results


def _load_validators() -> None:
    if ALL_VALIDATORS:
        return

    from src.services.bash_validators.control_char_validator import ControlCharValidator
    from src.services.bash_validators.unicode_whitespace_validator import UnicodeWhitespaceValidator
    from src.services.bash_validators.ifs_injection_validator import IFSInjectionValidator
    from src.services.bash_validators.command_substitution_validator import CommandSubstitutionValidator
    from src.services.bash_validators.redirect_validator import RedirectValidator
    from src.services.bash_validators.eval_like_validator import EvalLikeValidator
    from src.services.bash_validators.jq_system_validator import JqSystemValidator
    from src.services.bash_validators.proc_environ_validator import ProcEnvironValidator
    from src.services.bash_validators.variable_expansion_validator import VariableExpansionValidator
    from src.services.bash_validators.backslash_escape_validator import BackslashEscapeValidator
    from src.services.bash_validators.zsh_dangerous_validator import ZshDangerousValidator
    from src.services.bash_validators.brace_expansion_validator import BraceExpansionValidator
    from src.services.bash_validators.subcommand_limit_validator import SubcommandLimitValidator
    from src.services.bash_validators.git_commit_validator import GitCommitValidator
    from src.services.bash_validators.declaration_validator import DeclarationValidator
    from src.services.bash_validators.wrapper_command_validator import WrapperCommandValidator
    from src.services.bash_validators.empty_command_validator import EmptyCommandValidator
    from src.services.bash_validators.readonly_check_validator import ReadonlyCheckValidator
    from src.services.bash_validators.newline_hash_validator import NewlineHashValidator

    validator_classes = [
        ControlCharValidator,
        UnicodeWhitespaceValidator,
        IFSInjectionValidator,
        CommandSubstitutionValidator,
        RedirectValidator,
        EvalLikeValidator,
        JqSystemValidator,
        ProcEnvironValidator,
        VariableExpansionValidator,
        BackslashEscapeValidator,
        ZshDangerousValidator,
        BraceExpansionValidator,
        SubcommandLimitValidator,
        GitCommitValidator,
        DeclarationValidator,
        WrapperCommandValidator,
        EmptyCommandValidator,
        ReadonlyCheckValidator,
        NewlineHashValidator,
    ]

    for cls in validator_classes:
        register_validator(cls())
