from __future__ import annotations

from typing import Any


def snip_message(messages: list[dict[str, Any]], target_uuid: str) -> list[dict[str, Any]]:
    result = []
    for msg in messages:
        if msg.get("uuid") == target_uuid:
            snipped = dict(msg)
            snipped["is_absorbed_silently"] = True
            result.append(snipped)
        else:
            result.append(msg)
    return result


def restore_snipped_message(messages: list[dict[str, Any]], target_uuid: str) -> list[dict[str, Any]]:
    result = []
    for msg in messages:
        if msg.get("uuid") == target_uuid and msg.get("is_absorbed_silently"):
            restored = dict(msg)
            del restored["is_absorbed_silently"]
            result.append(restored)
        else:
            result.append(msg)
    return result


def get_snipped_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [msg for msg in messages if msg.get("is_absorbed_silently")]
