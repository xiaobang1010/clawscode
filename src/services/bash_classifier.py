from __future__ import annotations

import re
import shutil
import subprocess

SAFE_COMMANDS = {
    "ls", "dir", "cat", "head", "tail", "less", "more",
    "grep", "egrep", "fgrep", "rg", "ag", "ack",
    "find", "locate", "which", "whereis", "type",
    "echo", "printf", "pwd", "basename", "dirname",
    "wc", "sort", "uniq", "diff", "comm",
    "git", "gitlog", "gitstatus", "gitdiff", "gitbranch",
    "python", "python3", "node", "ruby", "perl",
    "pip", "pip3", "npm", "yarn", "pnpm",
    "tree", "du", "df", "free", "top", "ps",
    "env", "printenv", "set", "export",
    "whoami", "id", "uname", "hostname",
    "date", "cal", "uptime",
    "file", "stat", "md5sum", "sha256sum",
    "curl", "wget",
    "test", "[", "[[",
    "true", "false",
    "ruff", "mypy", "pylint", "flake8", "black",
    "pytest", "unittest", "npm test", "jest",
    "cargo", "go", "javac", "java",
}

SAFE_PATTERNS = [
    r"^git\s+(log|status|diff|branch|show|tag|remote|config|describe|rev-parse|shortlog|blame)",
    r"^python\s+-c\s+",
    r"^pip\s+(list|show|freeze|search)",
    r"^npm\s+(list|view|info|run|test|build|start)",
    r"^ls\b",
    r"^dir\b",
    r"^cat\b",
    r"^head\b",
    r"^tail\b",
    r"^grep\b",
    r"^rg\b",
    r"^find\b",
    r"^echo\b",
    r"^pwd$",
    r"^wc\b",
    r"^sort\b",
    r"^diff\b",
    r"^tree\b",
    r"^du\b",
    r"^file\b",
    r"^stat\b",
    r"^which\b",
    r"^type\b",
    r"^whoami$",
    r"^uname\b",
    r"^date\b",
    r"^env\b",
    r"^printenv\b",
    r"^test\b",
    r"^\[\b",
    r"^curl\b",
    r"^wget\b",
]

DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/",
    r"\brm\s+-rf\s+\*",
    r"\brm\s+-rf\s+~",
    r"\brm\s+-fr\s+/",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bformat\s+[A-Za-z]:",
    r"\bdel\s+/s\b",
    r"\brd\s+/s\b",
    r"\brmdir\s+/s\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r"\binit\s+[06]",
    r"\bsystemctl\s+(stop|disable|mask)",
    r"\bservice\s+\w+\s+stop",
    r"\biptables\s+-F",
    r"\bchmod\s+-R\s+777",
    r"\bchown\s+-R",
    r"(/\.\.)|(\.\./)",
    r">\s*/dev/sd",
    r"\bmv\s+/.*\s+/dev/null",
    r"\bkill\s+-9\s+1\b",
    r"\bkillall\b",
    r"\bpkill\s+-f",
    r"wget.*\|\s*(ba)?sh",
    r"curl.*\|\s*(ba)?sh",
]


def classify_bash_command(command: str) -> str:
    command = command.strip()
    if not command:
        return "safe"

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return "dangerous"

    base_cmd = command.split()[0] if command.split() else ""
    base_name = base_cmd.split("/")[-1] if "/" in base_cmd else base_cmd

    if base_name in SAFE_COMMANDS:
        return "safe"

    for pattern in SAFE_PATTERNS:
        if re.match(pattern, command):
            return "safe"

    if _is_git_safe(command):
        return "safe"

    return "unknown"


def _is_git_safe(command: str) -> bool:
    safe_git_subcommands = {
        "log", "status", "diff", "branch", "show", "tag",
        "remote", "config", "describe", "rev-parse", "shortlog",
        "blame", "stash", "list",
    }
    parts = command.split()
    if parts and parts[0] == "git" and len(parts) > 1:
        subcmd = parts[1]
        if subcmd in safe_git_subcommands:
            return True
    return False
