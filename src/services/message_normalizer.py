from __future__ import annotations

from typing import Any


def normalize_messages_for_api(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []

    filtered = _filter_valid_messages(messages)
    filtered = _filter_meta_messages(filtered)
    sanitize_error_tool_result_content(filtered)
    strip_oversized_content_blocks(filtered)
    merged = _merge_consecutive_user_messages(filtered)
    return reorder_attachments_for_api(merged)


def _filter_valid_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_types = {"user", "assistant", "tool"}
    result = []

    for msg in messages:
        msg_type = msg.get("type")
        if msg_type not in valid_types:
            continue

        if msg_type == "tool":
            if not msg.get("tool_use_id"):
                continue

        if msg_type == "user":
            content = msg.get("content")
            if content is None:
                continue
            if isinstance(content, str) and not content.strip():
                continue

        result.append(msg)

    return result


def _filter_meta_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [msg for msg in messages if not msg.get("is_meta") and not msg.get("is_visible_in_transcript_only")]


def _merge_consecutive_user_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []

    result = []

    for msg in messages:
        if msg.get("type") != "user":
            result.append(msg)
            continue

        if result and result[-1].get("type") == "user":
            last_user = result[-1]
            merged = _merge_two_user_messages(last_user, msg)
            result[-1] = merged
        else:
            result.append(msg.copy())

    return result


def _merge_two_user_messages(msg1: dict[str, Any], msg2: dict[str, Any]) -> dict[str, Any]:
    merged = msg1.copy()

    content1 = msg1.get("content")
    content2 = msg2.get("content")

    if isinstance(content1, str) and isinstance(content2, str):
        merged["content"] = content1 + "\n" + content2
    elif isinstance(content1, list) and isinstance(content2, list):
        merged["content"] = content1 + content2
    elif isinstance(content1, list) and isinstance(content2, str):
        merged["content"] = content1 + [{"type": "text", "text": content2}]
    elif isinstance(content1, str) and isinstance(content2, list):
        merged["content"] = [{"type": "text", "text": content1}] + content2
    else:
        merged["content"] = content1

    if msg2.get("uuid"):
        merged["uuid"] = msg2.get("uuid")

    return merged


def ensure_tool_result_pairing(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []

    result = []
    all_seen_tool_use_ids: set[str] = set()

    for i, msg in enumerate(messages):
        if msg.get("type") != "assistant":
            if msg.get("type") == "user":
                if result and result[-1].get("type") != "assistant":
                    content = msg.get("content")
                    if isinstance(content, list):
                        stripped = [
                            b for b in content
                            if not (isinstance(b, dict) and b.get("type") == "tool_result")
                        ]
                        if len(stripped) != len(content):
                            if stripped:
                                msg = {**msg, "content": stripped}
                            else:
                                continue
            result.append(msg)
            continue

        assistant_msg = msg.copy()
        content = msg.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]

        seen_tool_use_ids: set[str] = set()
        final_content = []

        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")

                if block_type == "tool_use":
                    tool_id = block.get("id")
                    if tool_id:
                        if tool_id in all_seen_tool_use_ids:
                            continue
                        all_seen_tool_use_ids.add(tool_id)
                        seen_tool_use_ids.add(tool_id)

                final_content.append(block)
            else:
                final_content.append(block)

        if not final_content:
            final_content = [{"type": "text", "text": "[Tool use interrupted]"}]

        assistant_msg["content"] = final_content
        result.append(assistant_msg)

        next_msg = messages[i + 1] if i + 1 < len(messages) else None
        existing_tool_result_ids: set[str] = set()

        if next_msg and next_msg.get("type") == "user":
            next_content = next_msg.get("content")
            if isinstance(next_content, list):
                for block in next_content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tr_id = block.get("tool_use_id")
                        if tr_id:
                            existing_tool_result_ids.add(tr_id)

        tool_use_ids = list(seen_tool_use_ids)
        missing_ids = [tid for tid in tool_use_ids if tid not in existing_tool_result_ids]

        if missing_ids:
            synthetic_content = []
            for tid in missing_ids:
                synthetic_content.append({
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "content": "[Tool result missing - conversation may have been interrupted]",
                })

            if synthetic_content:
                synthetic_user = {
                    "type": "user",
                    "content": synthetic_content,
                }
                result.append(synthetic_user)

    return result


def filter_incomplete_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []

    result = []

    for msg in messages:
        if msg.get("type") != "assistant":
            result.append(msg)
            continue

        content = msg.get("content")
        if isinstance(content, str):
            result.append(msg)
            continue

        if not isinstance(content, list):
            result.append(msg)
            continue

        has_tool_use = any(
            isinstance(b, dict) and b.get("type") == "tool_use"
            for b in content
        )

        if not has_tool_use:
            result.append(msg)
            continue

        has_content = any(
            isinstance(b, dict) and b.get("type") in ("text", "thinking")
            for b in content
        )

        if has_content:
            result.append(msg)
            continue

        continue

    return result


def normalize_tool_input_for_api(tool_input: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(tool_input, dict):
        return tool_input

    normalized = {}
    for key, value in tool_input.items():
        if isinstance(value, str):
            normalized[key] = value
        elif isinstance(value, (int, float, bool)):
            normalized[key] = value
        elif isinstance(value, dict):
            normalized[key] = normalize_tool_input_for_api(value)
        elif isinstance(value, list):
            normalized[key] = [
                normalize_tool_input_for_api(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            normalized[key] = str(value)

    return normalized


def _is_attachment_message(msg: dict[str, Any]) -> bool:
    if msg.get("type") != "user":
        return False
    content = msg.get("content")
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") == "attachment"
            for b in content
        )
    return False


def _has_tool_result(msg: dict[str, Any]) -> bool:
    content = msg.get("content")
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in content
        )
    return False


def reorder_attachments_for_api(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []

    reversed_result: list[dict[str, Any]] = []
    pending_attachments: list[dict[str, Any]] = []

    for msg in reversed(messages):
        is_stop = (
            msg.get("type") == "assistant"
            or (msg.get("type") == "user" and _has_tool_result(msg))
        )

        if _is_attachment_message(msg):
            pending_attachments.append(msg)
            continue

        if is_stop:
            for att in reversed(pending_attachments):
                reversed_result.append(att)
            pending_attachments = []
            reversed_result.append(msg)
        else:
            reversed_result.append(msg)

    for att in reversed(pending_attachments):
        reversed_result.append(att)

    reversed_result.reverse()
    return reversed_result


_ERROR_TO_BLOCK_TYPES: dict[str, set[str]] = {
    "pdf": {"document"},
    "image": {"image"},
    "media": {"image", "document"},
    "request": {"document", "image"},
}

_ERROR_KEYWORDS: list[tuple[str, str]] = [
    ("pdf", "pdf"),
    ("image", "image"),
    ("media size", "media"),
    ("request too large", "request"),
    ("prompt too long", "request"),
    ("too large", "media"),
]


def _classify_error_type(error_text: str) -> str | None:
    lower = error_text.lower()
    for keyword, error_type in _ERROR_KEYWORDS:
        if keyword in lower:
            return error_type
    return None


def strip_oversized_content_blocks(messages: list[dict[str, Any]]) -> None:
    strip_targets: dict[str, set[str]] = {}

    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            if not block.get("is_error"):
                continue
            error_text = ""
            if isinstance(block.get("content"), str):
                error_text = block["content"]
            elif isinstance(block.get("content"), list):
                for sub in block["content"]:
                    if isinstance(sub, dict) and sub.get("type") == "text":
                        error_text += sub.get("text", "")
            error_type = _classify_error_type(error_text)
            if error_type is None:
                continue
            block_types = _ERROR_TO_BLOCK_TYPES.get(error_type, set())
            source_uuid = block.get("source_uuid") or block.get("_source_user_uuid")
            if source_uuid:
                existing = strip_targets.get(source_uuid, set())
                existing.update(block_types)
                strip_targets[source_uuid] = existing

    if not strip_targets:
        return

    for msg in messages:
        msg_uuid = msg.get("uuid", "")
        if msg_uuid not in strip_targets:
            continue
        if not msg.get("is_meta"):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        block_types_to_strip = strip_targets[msg_uuid]
        filtered = [
            b for b in content
            if not (isinstance(b, dict) and b.get("type") in block_types_to_strip)
        ]
        msg["content"] = filtered


def sanitize_error_tool_result_content(messages: list[dict[str, Any]]) -> None:
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        has_error_tool_result = False
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                has_error_tool_result = True
                break
        if not has_error_tool_result:
            continue
        filtered = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                inner = block.get("content")
                if isinstance(inner, list):
                    text_only = [b for b in inner if isinstance(b, dict) and b.get("type") == "text"]
                    if len(text_only) != len(inner):
                        block = {**block, "content": text_only}
                filtered.append(block)
            else:
                filtered.append(block)
        msg["content"] = filtered
