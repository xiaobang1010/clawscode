from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_PER_MESSAGE_BUDGET = 100 * 1024


@dataclass
class ToolResultCandidate:
    tool_use_id: str
    size: int
    content: str
    message_index: int
    tool_name: str = ""


@dataclass
class ToolResultReplacementRecord:
    tool_use_id: str
    replacement: str
    original_size: int


@dataclass
class ToolResultBudgetState:
    seen_ids: set[str] = field(default_factory=set)
    replacements: dict[str, str] = field(default_factory=dict)
    per_message_budget: int = DEFAULT_PER_MESSAGE_BUDGET


def enforce_tool_result_budget(
    messages: list[dict[str, Any]],
    state: ToolResultBudgetState,
    skip_tool_names: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[ToolResultReplacementRecord]]:
    if skip_tool_names is None:
        skip_tool_names = set()

    candidates = _collect_candidates_by_message(messages)
    tool_name_map = _build_tool_name_map(messages) if skip_tool_names else {}

    def should_skip(tool_use_id: str) -> bool:
        if not tool_name_map:
            return False
        return tool_name_map.get(tool_use_id, "") in skip_tool_names

    replacement_map: dict[str, str] = {}
    to_persist: list[ToolResultCandidate] = []
    newly_replaced: list[ToolResultReplacementRecord] = []

    for candidate_list in candidates:
        must_reapply, frozen, fresh = _partition_by_prior_decision(
            candidate_list, state
        )

        for c in must_reapply:
            if c.tool_use_id in state.replacements:
                replacement_map[c.tool_use_id] = state.replacements[c.tool_use_id]

        if not fresh:
            for c in candidate_list:
                state.seen_ids.add(c.tool_use_id)
            continue

        skipped = [c for c in fresh if should_skip(c.tool_use_id)]
        for c in skipped:
            state.seen_ids.add(c.tool_use_id)

        eligible = [c for c in fresh if not should_skip(c.tool_use_id)]

        frozen_size = sum(c.size for c in frozen)
        fresh_size = sum(c.size for c in eligible)

        limit = state.per_message_budget
        selected = (
            _select_fresh_to_replace(eligible, frozen_size, limit)
            if frozen_size + fresh_size > limit
            else []
        )

        selected_ids = {c.tool_use_id for c in selected}
        for c in candidate_list:
            if c.tool_use_id not in selected_ids:
                state.seen_ids.add(c.tool_use_id)

        to_persist.extend(selected)

    if not replacement_map and not to_persist:
        return messages, []

    for candidate in to_persist:
        state.seen_ids.add(candidate.tool_use_id)

        replacement = _build_replacement(candidate)
        if replacement:
            replacement_map[candidate.tool_use_id] = replacement
            state.replacements[candidate.tool_use_id] = replacement
            newly_replaced.append(
                ToolResultReplacementRecord(
                    tool_use_id=candidate.tool_use_id,
                    replacement=replacement,
                    original_size=candidate.size,
                )
            )

    if not replacement_map:
        return messages, []

    result_messages = _replace_tool_result_contents(messages, replacement_map)
    return result_messages, newly_replaced


def _collect_candidates_by_message(
    messages: list[dict[str, Any]],
) -> list[list[ToolResultCandidate]]:
    result = []

    for msg_idx, msg in enumerate(messages):
        if msg.get("type") != "user":
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            continue

        candidates = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id", "")
                block_content = block.get("content", "")
                size = len(block_content) if isinstance(block_content, str) else 0

                candidates.append(
                    ToolResultCandidate(
                        tool_use_id=tool_use_id,
                        size=size,
                        content=block_content if isinstance(block_content, str) else "",
                        message_index=msg_idx,
                    )
                )

        if candidates:
            result.append(candidates)

    return result


def _build_tool_name_map(messages: list[dict[str, Any]]) -> dict[str, str]:
    tool_name_map = {}

    for msg in messages:
        if msg.get("type") != "assistant":
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_id = block.get("id", "")
                tool_name = block.get("name", "")
                if tool_id and tool_name:
                    tool_name_map[tool_id] = tool_name

    return tool_name_map


def _partition_by_prior_decision(
    candidates: list[ToolResultCandidate],
    state: ToolResultBudgetState,
) -> tuple[list[ToolResultCandidate], list[ToolResultCandidate], list[ToolResultCandidate]]:
    must_reapply = []
    frozen = []
    fresh = []

    for c in candidates:
        if c.tool_use_id in state.replacements:
            must_reapply.append(c)
        elif c.tool_use_id in state.seen_ids:
            frozen.append(c)
        else:
            fresh.append(c)

    return must_reapply, frozen, fresh


def _select_fresh_to_replace(
    fresh: list[ToolResultCandidate],
    frozen_size: int,
    limit: int,
) -> list[ToolResultCandidate]:
    if not fresh:
        return []

    fresh_sorted = sorted(fresh, key=lambda c: c.size, reverse=True)

    selected = []
    current_size = frozen_size

    for candidate in fresh_sorted:
        if current_size + candidate.size > limit:
            selected.append(candidate)
        else:
            current_size += candidate.size

    return selected


def _build_replacement(candidate: ToolResultCandidate) -> str | None:
    if not candidate.content:
        return None

    content = candidate.content
    head_size = min(1000, len(content) // 4)
    tail_size = min(1000, len(content) // 4)

    head = content[:head_size]
    tail = content[-tail_size:] if tail_size > 0 else ""

    replacement = f"{head}\n\n... [truncated, {candidate.size} bytes total] ...\n\n{tail}"
    return replacement


def _replace_tool_result_contents(
    messages: list[dict[str, Any]],
    replacement_map: dict[str, str],
) -> list[dict[str, Any]]:
    result = []

    for msg in messages:
        if msg.get("type") != "user":
            result.append(msg)
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue

        new_content = []
        modified = False

        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id", "")
                if tool_use_id in replacement_map:
                    new_block = {**block, "content": replacement_map[tool_use_id]}
                    new_content.append(new_block)
                    modified = True
                else:
                    new_content.append(block)
            else:
                new_content.append(block)

        if modified:
            result.append({**msg, "content": new_content})
        else:
            result.append(msg)

    return result


def calculate_message_tool_result_size(message: dict[str, Any]) -> int:
    if message.get("type") != "user":
        return 0

    content = message.get("content")
    if not isinstance(content, list):
        return 0

    total_size = 0
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            block_content = block.get("content", "")
            if isinstance(block_content, str):
                total_size += len(block_content)

    return total_size


def get_budget_usage_report(
    messages: list[dict[str, Any]],
    state: ToolResultBudgetState,
) -> dict[str, Any]:
    candidates = _collect_candidates_by_message(messages)

    total_size = 0
    total_replaced = 0
    messages_over_budget = 0

    for candidate_list in candidates:
        msg_size = sum(c.size for c in candidate_list)
        total_size += msg_size

        if msg_size > state.per_message_budget:
            messages_over_budget += 1

        for c in candidate_list:
            if c.tool_use_id in state.replacements:
                total_replaced += 1

    return {
        "total_tool_results": sum(len(c) for c in candidates),
        "total_size_bytes": total_size,
        "total_replaced": total_replaced,
        "messages_over_budget": messages_over_budget,
        "per_message_budget": state.per_message_budget,
    }
