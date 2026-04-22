from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import tiktoken


@lru_cache(maxsize=1)
def _get_encoder():
    return tiktoken.encoding_for_model("gpt-4")


def count_tokens(messages: list[dict]) -> int:
    enc = _get_encoder()
    total = 0
    for msg in messages:
        total += len(enc.encode(str(msg)))
    return total


def has_thinking_blocks(messages: list[dict]) -> bool:
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            if "<thinking>" in content or "</thinking>" in content:
                return True
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "thinking":
                        return True
                    if block.get("type") == "text" and (
                        "<thinking>" in block.get("text", "") or "</thinking>" in block.get("text", "")
                    ):
                        return True
    return False


def count_thinking_tokens(messages: list[dict]) -> int:
    enc = _get_encoder()
    total = 0

    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            if "<thinking>" in content:
                start = content.find("<thinking>")
                end = content.find("</thinking>")
                if end > start:
                    thinking_content = content[start:end + 11]
                    total += len(enc.encode(thinking_content))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    thinking_text = block.get("thinking", "")
                    total += len(enc.encode(thinking_text))

    return total


FILE_TYPE_DENSITY_MAP: dict[str, float] = {
    ".json": 0.5,
    ".jsonl": 0.5,
    ".yaml": 0.6,
    ".yml": 0.6,
    ".xml": 0.6,
    ".html": 0.6,
    ".css": 0.7,
    ".scss": 0.7,
    ".js": 0.7,
    ".ts": 0.7,
    ".jsx": 0.7,
    ".tsx": 0.7,
    ".py": 0.7,
    ".java": 0.7,
    ".go": 0.7,
    ".rs": 0.7,
    ".c": 0.7,
    ".cpp": 0.7,
    ".h": 0.7,
    ".hpp": 0.7,
    ".md": 1.5,
    ".txt": 1.5,
    ".rst": 1.5,
    ".csv": 0.8,
    ".sql": 0.7,
    ".sh": 0.8,
    ".bash": 0.8,
    ".ps1": 0.8,
    ".toml": 0.6,
    ".ini": 0.8,
    ".cfg": 0.8,
    ".env": 0.8,
}

DEFAULT_BYTES_PER_TOKEN = 4


def bytes_per_token_for_file_type(file_path: str | Path) -> float:
    path = Path(file_path) if isinstance(file_path, str) else file_path
    ext = path.suffix.lower()

    if ext in FILE_TYPE_DENSITY_MAP:
        return DEFAULT_BYTES_PER_TOKEN * FILE_TYPE_DENSITY_MAP[ext]

    return DEFAULT_BYTES_PER_TOKEN


def estimate_tokens_for_file(file_path: str | Path) -> int:
    path = Path(file_path) if isinstance(file_path, str) else file_path

    if not path.exists():
        return 0

    try:
        file_size = path.stat().st_size
        bytes_per_token = bytes_per_token_for_file_type(path)
        return max(1, int(file_size / bytes_per_token))
    except OSError:
        return 0


def estimate_tokens_for_content(content: str, file_path: str | Path | None = None) -> int:
    if not content:
        return 0

    if file_path:
        bytes_per_token = bytes_per_token_for_file_type(file_path)
        return max(1, int(len(content.encode("utf-8")) / bytes_per_token))

    enc = _get_encoder()
    return len(enc.encode(content))
