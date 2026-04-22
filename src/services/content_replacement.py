from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentReplacementRecord:
    kind: str = "tool-result"
    tool_use_id: str = ""
    replacement: str = ""


@dataclass
class ContentReplacementState:
    seen_ids: set[str] = field(default_factory=set)
    replacements: dict[str, str] = field(default_factory=dict)


def create_content_replacement_state() -> ContentReplacementState:
    return ContentReplacementState()


def clone_content_replacement_state(source: ContentReplacementState) -> ContentReplacementState:
    return ContentReplacementState(
        seen_ids=set(source.seen_ids),
        replacements=dict(source.replacements),
    )


def provision_content_replacement_state(
    initial_messages: list[dict[str, Any]] | None = None,
    initial_content_replacements: list[ContentReplacementRecord] | None = None,
) -> ContentReplacementState | None:
    if initial_messages:
        return reconstruct_content_replacement_state(
            initial_messages,
            initial_content_replacements or [],
        )
    return create_content_replacement_state()


def reconstruct_content_replacement_state(
    messages: list[dict[str, Any]],
    content_replacements: list[ContentReplacementRecord],
) -> ContentReplacementState:
    state = create_content_replacement_state()

    for msg in messages:
        _collect_tool_result_ids(msg, state.seen_ids)

    for record in content_replacements:
        if record.tool_use_id:
            state.seen_ids.add(record.tool_use_id)
            if record.replacement:
                state.replacements[record.tool_use_id] = record.replacement

    return state


def _collect_tool_result_ids(message: dict[str, Any], seen_ids: set[str]) -> None:
    if message.get("type") != "user":
        return

    content = message.get("content")
    if not isinstance(content, list):
        return

    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tool_use_id = block.get("tool_use_id", "")
            if tool_use_id:
                seen_ids.add(tool_use_id)


def record_replacement(
    state: ContentReplacementState,
    tool_use_id: str,
    replacement: str,
) -> None:
    state.seen_ids.add(tool_use_id)
    state.replacements[tool_use_id] = replacement


def get_replacement(
    state: ContentReplacementState,
    tool_use_id: str,
) -> str | None:
    return state.replacements.get(tool_use_id)


def is_seen(state: ContentReplacementState, tool_use_id: str) -> bool:
    return tool_use_id in state.seen_ids


def has_replacement(state: ContentReplacementState, tool_use_id: str) -> bool:
    return tool_use_id in state.replacements


def clear_replacement(state: ContentReplacementState, tool_use_id: str) -> bool:
    if tool_use_id in state.replacements:
        del state.replacements[tool_use_id]
        return True
    return False


def get_all_replacements(state: ContentReplacementState) -> list[ContentReplacementRecord]:
    return [
        ContentReplacementRecord(
            kind="tool-result",
            tool_use_id=tool_use_id,
            replacement=replacement,
        )
        for tool_use_id, replacement in state.replacements.items()
    ]


def merge_content_replacement_states(
    parent: ContentReplacementState,
    child: ContentReplacementState,
) -> ContentReplacementState:
    merged = clone_content_replacement_state(parent)

    for tool_use_id in child.seen_ids:
        merged.seen_ids.add(tool_use_id)

    for tool_use_id, replacement in child.replacements.items():
        merged.replacements[tool_use_id] = replacement

    return merged


def serialize_content_replacement_state(state: ContentReplacementState) -> dict[str, Any]:
    return {
        "seen_ids": list(state.seen_ids),
        "replacements": [
            {
                "kind": "tool-result",
                "tool_use_id": tool_use_id,
                "replacement": replacement,
            }
            for tool_use_id, replacement in state.replacements.items()
        ],
    }


def deserialize_content_replacement_state(data: dict[str, Any]) -> ContentReplacementState:
    state = create_content_replacement_state()

    seen_ids = data.get("seen_ids", [])
    if isinstance(seen_ids, list):
        state.seen_ids = set(seen_ids)

    replacements = data.get("replacements", [])
    if isinstance(replacements, list):
        for record in replacements:
            if isinstance(record, dict):
                tool_use_id = record.get("tool_use_id", "")
                replacement = record.get("replacement", "")
                if tool_use_id and replacement:
                    state.replacements[tool_use_id] = replacement

    return state


def check_cache_stability(
    state: ContentReplacementState,
    tool_use_id: str,
    current_content: str,
) -> bool:
    if tool_use_id not in state.replacements:
        return True

    return state.replacements[tool_use_id] == current_content


def get_state_statistics(state: ContentReplacementState) -> dict[str, int]:
    return {
        "seen_ids_count": len(state.seen_ids),
        "replacements_count": len(state.replacements),
    }
