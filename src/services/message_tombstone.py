from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .message_uuid import generate_uuid


@dataclass
class TombstoneMessage:
    target_uuid: str
    reason: str = ""
    uuid: str = field(default_factory=generate_uuid)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tombstone",
            "uuid": self.uuid,
            "target_uuid": self.target_uuid,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TombstoneMessage:
        return cls(
            target_uuid=data.get("target_uuid", ""),
            reason=data.get("reason", ""),
            uuid=data.get("uuid", generate_uuid()),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


def create_tombstone_message(target_uuid: str, reason: str = "") -> dict[str, Any]:
    tombstone = TombstoneMessage(target_uuid=target_uuid, reason=reason)
    return tombstone.to_dict()


def is_tombstone_message(message: dict[str, Any]) -> bool:
    return message.get("type") == "tombstone"


def delete_message_with_tombstone(
    messages: list[dict[str, Any]],
    target_uuid: str,
    reason: str = "",
) -> list[dict[str, Any]]:
    tombstone = create_tombstone_message(target_uuid, reason)

    result = []
    found = False

    for msg in messages:
        if msg.get("uuid") == target_uuid:
            found = True
            result.append(tombstone)
        else:
            result.append(msg)

    if not found:
        result.append(tombstone)

    return result


def filter_tombstone_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tombstone_targets = set()

    for msg in messages:
        if is_tombstone_message(msg):
            target_uuid = msg.get("target_uuid")
            if target_uuid:
                tombstone_targets.add(target_uuid)

    result = []
    for msg in messages:
        if is_tombstone_message(msg):
            continue

        msg_uuid = msg.get("uuid")
        if msg_uuid and msg_uuid in tombstone_targets:
            continue

        result.append(msg)

    return result


def get_tombstone_targets(messages: list[dict[str, Any]]) -> set[str]:
    targets = set()

    for msg in messages:
        if is_tombstone_message(msg):
            target_uuid = msg.get("target_uuid")
            if target_uuid:
                targets.add(target_uuid)

    return targets


def apply_tombstones(
    messages: list[dict[str, Any]],
    tombstones: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tombstone_targets = get_tombstone_targets(tombstones)

    result = []
    for msg in messages:
        msg_uuid = msg.get("uuid")
        if msg_uuid and msg_uuid in tombstone_targets:
            continue
        result.append(msg)

    return result


def remove_message_chain_with_tombstone(
    messages: list[dict[str, Any]],
    target_uuid: str,
    reason: str = "",
) -> list[dict[str, Any]]:
    uuid_to_children: dict[str, list[str]] = {}
    uuid_to_msg: dict[str, dict[str, Any]] = {}

    for msg in messages:
        msg_uuid = msg.get("uuid")
        parent_uuid = msg.get("parent_uuid")

        if msg_uuid:
            uuid_to_msg[msg_uuid] = msg
            uuid_to_children[msg_uuid] = uuid_to_children.get(msg_uuid, [])

            if parent_uuid:
                if parent_uuid not in uuid_to_children:
                    uuid_to_children[parent_uuid] = []
                uuid_to_children[parent_uuid].append(msg_uuid)

    def get_descendants(uuid: str) -> set[str]:
        descendants = {uuid}
        for child_uuid in uuid_to_children.get(uuid, []):
            descendants.update(get_descendants(child_uuid))
        return descendants

    to_remove = get_descendants(target_uuid)

    result = []
    for msg in messages:
        msg_uuid = msg.get("uuid")
        if msg_uuid in to_remove:
            continue
        result.append(msg)

    tombstone = create_tombstone_message(target_uuid, reason)
    result.append(tombstone)

    return result
