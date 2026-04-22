from __future__ import annotations

from typing import Any


def normalize_messages_for_api(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []

    filtered = _filter_valid_messages(messages)
    merged = _merge_consecutive_user_messages(filtered)
    return merged


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
