from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


def generate_uuid() -> str:
    return str(uuid.uuid4())


def derive_uuid(parent_uuid: str, index: int) -> str:
    hex_str = format(index, '012x')
    return parent_uuid[:24] + hex_str


def _is_progress_message(message: dict[str, Any]) -> bool:
    return message.get("type") == "progress" or message.get("_type") == "progress"


@dataclass
class MessageChain:
    messages: list[dict[str, Any]] = field(default_factory=list)
    uuid_to_index: dict[str, int] = field(default_factory=dict)

    def add_message(self, message: dict[str, Any]) -> str:
        msg_uuid = message["uuid"] if "uuid" in message else generate_uuid()
        parent_uuid = None

        if not _is_progress_message(message) and self.messages:
            last_msg = self.messages[-1]
            parent_uuid = last_msg.get("uuid")

        message["uuid"] = msg_uuid
        message["parent_uuid"] = parent_uuid

        self.messages.append(message)
        self.uuid_to_index[msg_uuid] = len(self.messages) - 1

        return msg_uuid

    def get_message_by_uuid(self, msg_uuid: str) -> dict[str, Any] | None:
        index = self.uuid_to_index.get(msg_uuid)
        if index is not None:
            return self.messages[index]
        return None

    def get_children(self, parent_uuid: str) -> list[dict[str, Any]]:
        children = []
        for msg in self.messages:
            if msg.get("parent_uuid") == parent_uuid:
                children.append(msg)
        return children

    def get_ancestors(self, msg_uuid: str) -> list[dict[str, Any]]:
        ancestors = []
        current = self.get_message_by_uuid(msg_uuid)

        while current:
            parent_uuid = current.get("parent_uuid")
            if parent_uuid:
                parent = self.get_message_by_uuid(parent_uuid)
                if parent:
                    ancestors.insert(0, parent)
                    current = parent
                else:
                    break
            else:
                break

        return ancestors

    def get_descendants(self, msg_uuid: str) -> list[dict[str, Any]]:
        descendants = []
        children = self.get_children(msg_uuid)

        for child in children:
            descendants.append(child)
            descendants.extend(self.get_descendants(child.get("uuid")))

        return descendants

    def rebuild_chain(self, messages: list[dict[str, Any]]) -> None:
        self.messages = []
        self.uuid_to_index = {}

        for msg in messages:
            msg_uuid = msg["uuid"] if "uuid" in msg else generate_uuid()
            msg["uuid"] = msg_uuid

            if self.messages:
                msg["parent_uuid"] = self.messages[-1].get("uuid")
            else:
                msg["parent_uuid"] = None

            self.messages.append(msg)
            self.uuid_to_index[msg_uuid] = len(self.messages) - 1

    def get_chain_to(self, msg_uuid: str) -> list[dict[str, Any]]:
        chain = []
        current = self.get_message_by_uuid(msg_uuid)

        while current:
            chain.insert(0, current)
            parent_uuid = current.get("parent_uuid")
            if parent_uuid:
                current = self.get_message_by_uuid(parent_uuid)
            else:
                break

        return chain

    def get_leaf_messages(self) -> list[dict[str, Any]]:
        leaf_uuids = set()

        for msg in self.messages:
            msg_uuid = msg.get("uuid")
            if msg_uuid:
                leaf_uuids.add(msg_uuid)

        for msg in self.messages:
            parent_uuid = msg.get("parent_uuid")
            if parent_uuid and parent_uuid in leaf_uuids:
                leaf_uuids.discard(parent_uuid)

        return [self.get_message_by_uuid(u) for u in leaf_uuids if self.get_message_by_uuid(u)]

    def remove_message_and_descendants(self, msg_uuid: str) -> list[str]:
        removed_uuids = [msg_uuid]
        descendants = self.get_descendants(msg_uuid)
        removed_uuids.extend(d.get("uuid") for d in descendants if d.get("uuid"))

        for remove_uuid in removed_uuids:
            if remove_uuid in self.uuid_to_index:
                index = self.uuid_to_index[remove_uuid]
                if 0 <= index < len(self.messages):
                    self.messages[index] = {}
                del self.uuid_to_index[remove_uuid]

        self.messages = [m for m in self.messages if m]
        self.uuid_to_index = {}
        for i, msg in enumerate(self.messages):
            if msg.get("uuid"):
                self.uuid_to_index[msg["uuid"]] = i

        return removed_uuids


def create_message_with_uuid(
    message: dict[str, Any],
    parent_uuid: str | None = None,
) -> dict[str, Any]:
    msg_uuid = message["uuid"] if "uuid" in message else generate_uuid()
    message["uuid"] = msg_uuid
    message["parent_uuid"] = parent_uuid
    return message


def find_message_by_uuid(messages: list[dict[str, Any]], msg_uuid: str) -> dict[str, Any] | None:
    for msg in messages:
        if msg.get("uuid") == msg_uuid:
            return msg
    return None


def get_message_chain(messages: list[dict[str, Any]]) -> dict[str, list[str]]:
    uuid_to_children: dict[str, list[str]] = {}
    uuid_to_parent: dict[str, str | None] = {}

    for msg in messages:
        msg_uuid = msg.get("uuid")
        parent_uuid = msg.get("parent_uuid")

        if msg_uuid:
            uuid_to_parent[msg_uuid] = parent_uuid
            uuid_to_children[msg_uuid] = uuid_to_children.get(msg_uuid, [])

            if parent_uuid:
                if parent_uuid not in uuid_to_children:
                    uuid_to_children[parent_uuid] = []
                uuid_to_children[parent_uuid].append(msg_uuid)

    return uuid_to_children
