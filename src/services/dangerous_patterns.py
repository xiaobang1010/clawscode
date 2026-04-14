from __future__ import annotations

import re

DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?(-[a-zA-Z]*r[a-zA-Z]*\s+)?/(\s|$)", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\s+\*", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\s+~", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r"\bformat\s+[A-Za-z]:", re.IGNORECASE),
    re.compile(r"\bdel\s+/s\b", re.IGNORECASE),
    re.compile(r"\brd\s+/s\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r"\bhalt\b", re.IGNORECASE),
    re.compile(r"\bpoweroff\b", re.IGNORECASE),
    re.compile(r"\binit\s+[06]", re.IGNORECASE),
    re.compile(r"\biptables\s+-F", re.IGNORECASE),
    re.compile(r"\bchmod\s+-R\s+777", re.IGNORECASE),
    re.compile(r">\s*/dev/sd", re.IGNORECASE),
    re.compile(r"wget.*\|\s*(ba)?sh", re.IGNORECASE),
    re.compile(r"curl.*\|\s*(ba)?sh", re.IGNORECASE),
    re.compile(r"\bkill\s+-9\s+1\b", re.IGNORECASE),
    re.compile(r"\bkillall\b", re.IGNORECASE),
    re.compile(r"\bsystemctl\s+(stop|disable|mask)\b", re.IGNORECASE),
    re.compile(r"\bservice\s+\w+\s+stop\b", re.IGNORECASE),
    re.compile(r"\bmv\s+/.*\s+/dev/null", re.IGNORECASE),
    re.compile(r"\bchown\s+-R\s+", re.IGNORECASE),
]

DANGEROUS_FILE_PATTERNS = [
    re.compile(r"/etc/passwd", re.IGNORECASE),
    re.compile(r"/etc/shadow", re.IGNORECASE),
    re.compile(r"/etc/sudoers", re.IGNORECASE),
    re.compile(r"/boot/", re.IGNORECASE),
    re.compile(r"/proc/", re.IGNORECASE),
    re.compile(r"/sys/", re.IGNORECASE),
    re.compile(r"C:\\Windows\\System32", re.IGNORECASE),
    re.compile(r"C:\\Program Files", re.IGNORECASE),
]


def is_dangerous(command: str) -> bool:
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return True
    return False


def is_dangerous_path(path: str) -> bool:
    for pattern in DANGEROUS_FILE_PATTERNS:
        if pattern.search(path):
            return True
    return False


def classify_file_operation(operation: str, path: str) -> str:
    if is_dangerous_path(path):
        return "dangerous"

    if operation in ("read", "stat", "list"):
        return "safe"

    if operation in ("write", "delete", "move", "rename"):
        return "cautious"

    return "unknown"
