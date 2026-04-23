from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    import chardet
except ImportError:
    chardet = None


@dataclass
class CachedFileData:
    content: str
    encoding: str
    mtime: float


class FileReadCache:
    max_cache_size = 1000

    def __init__(self) -> None:
        self._cache: dict[str, CachedFileData] = {}
        self._hits = 0
        self._misses = 0

    def _normalize_path(self, file_path: str) -> str:
        return os.path.normpath(file_path)

    def _detect_encoding(self, raw_bytes: bytes) -> str:
        if chardet is not None:
            result = chardet.detect(raw_bytes)
            if result and result.get("encoding"):
                return result["encoding"]
        return "utf-8"

    def read_file(self, file_path: str) -> str | None:
        normalized_path = self._normalize_path(file_path)
        try:
            stat_result = os.stat(normalized_path)
            current_mtime = stat_result.st_mtime
        except OSError:
            return None

        cached = self._cache.get(normalized_path)
        if cached is not None and cached.mtime == current_mtime:
            self._hits += 1
            return cached.content

        self._misses += 1

        try:
            with open(normalized_path, "rb") as f:
                raw_bytes = f.read()
        except OSError:
            return None

        encoding = self._detect_encoding(raw_bytes)
        try:
            content = raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            content = raw_bytes.decode("utf-8", errors="replace")

        if normalized_path not in self._cache and len(self._cache) >= self.max_cache_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[normalized_path] = CachedFileData(
            content=content,
            encoding=encoding,
            mtime=current_mtime,
        )
        return content

    def invalidate(self, file_path: str) -> None:
        normalized_path = self._normalize_path(file_path)
        self._cache.pop(normalized_path, None)

    def clear(self) -> None:
        self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }


file_read_cache = FileReadCache()
