from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterator


DEFAULT_MAX_ENTRIES = 100
DEFAULT_MAX_SIZE_BYTES = 25 * 1024 * 1024


@dataclass
class FileState:
    content: str
    timestamp: float
    offset: int | None = None
    limit: int | None = None
    is_partial_view: bool = False


class FileStateCache:
    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
    ):
        self._max_entries = max_entries
        self._max_size_bytes = max_size_bytes
        self._cache: OrderedDict[str, FileState] = OrderedDict()
        self._current_size = 0
        self._hits = 0
        self._misses = 0

    def _normalize_path(self, path: str) -> str:
        normalized = os.path.normpath(path)
        if os.name == "nt":
            normalized = normalized.lower()
        return normalized

    def _calculate_size(self, state: FileState) -> int:
        return max(1, len(state.content.encode("utf-8")))

    def _evict_if_needed(self, required_size: int) -> None:
        while (
            self._current_size + required_size > self._max_size_bytes
            or len(self._cache) >= self._max_entries
        ) and self._cache:
            oldest_key = next(iter(self._cache))
            oldest_state = self._cache.pop(oldest_key)
            self._current_size -= self._calculate_size(oldest_state)

    def get(self, key: str) -> FileState | None:
        normalized_key = self._normalize_path(key)
        if normalized_key in self._cache:
            self._hits += 1
            state = self._cache.pop(normalized_key)
            self._cache[normalized_key] = state
            return state
        self._misses += 1
        return None

    def set(self, key: str, value: FileState) -> None:
        normalized_key = self._normalize_path(key)
        size = self._calculate_size(value)

        if normalized_key in self._cache:
            old_state = self._cache.pop(normalized_key)
            self._current_size -= self._calculate_size(old_state)
        else:
            self._evict_if_needed(size)

        self._cache[normalized_key] = value
        self._current_size += size

    def has(self, key: str) -> bool:
        normalized_key = self._normalize_path(key)
        return normalized_key in self._cache

    def delete(self, key: str) -> bool:
        normalized_key = self._normalize_path(key)
        if normalized_key in self._cache:
            state = self._cache.pop(normalized_key)
            self._current_size -= self._calculate_size(state)
            return True
        return False

    def clear(self) -> None:
        self._cache.clear()
        self._current_size = 0

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def max_size_bytes(self) -> int:
        return self._max_size_bytes

    @property
    def current_size_bytes(self) -> int:
        return self._current_size

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def keys(self) -> Iterator[str]:
        return iter(self._cache.keys())

    def entries(self) -> Iterator[tuple[str, FileState]]:
        return iter(self._cache.items())

    def values(self) -> Iterator[FileState]:
        return iter(self._cache.values())

    def dump(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (key, {
                "content": state.content,
                "timestamp": state.timestamp,
                "offset": state.offset,
                "limit": state.limit,
                "is_partial_view": state.is_partial_view,
            })
            for key, state in self._cache.items()
        ]

    def load(self, entries: list[tuple[str, dict[str, Any]]]) -> None:
        self.clear()
        for key, data in entries:
            state = FileState(
                content=data.get("content", ""),
                timestamp=data.get("timestamp", 0.0),
                offset=data.get("offset"),
                limit=data.get("limit"),
                is_partial_view=data.get("is_partial_view", False),
            )
            self.set(key, state)


def create_file_state_cache(
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
) -> FileStateCache:
    return FileStateCache(max_entries, max_size_bytes)


def cache_to_object(cache: FileStateCache) -> dict[str, dict[str, Any]]:
    return {
        key: {
            "content": state.content,
            "timestamp": state.timestamp,
            "offset": state.offset,
            "limit": state.limit,
            "is_partial_view": state.is_partial_view,
        }
        for key, state in cache.entries()
    }


def cache_keys(cache: FileStateCache) -> list[str]:
    return list(cache.keys())


def clone_file_state_cache(cache: FileStateCache) -> FileStateCache:
    cloned = create_file_state_cache(cache.max_entries, cache.max_size_bytes)
    cloned.load(cache.dump())
    return cloned


def merge_file_state_caches(
    first: FileStateCache,
    second: FileStateCache,
) -> FileStateCache:
    merged = clone_file_state_cache(first)
    for file_path, file_state in second.entries():
        existing = merged.get(file_path)
        if existing is None or file_state.timestamp > existing.timestamp:
            merged.set(file_path, file_state)
    return merged
