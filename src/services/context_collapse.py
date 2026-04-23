from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

COMMIT_THRESHOLD_RATIO = 0.90
BLOCK_THRESHOLD_RATIO = 0.95


@dataclass
class CollapseCommit:
    collapse_id: str
    summary_uuid: str
    summary_content: str
    summary: str
    first_archived_uuid: str
    last_archived_uuid: str


@dataclass
class StagedCollapse:
    start_uuid: str
    end_uuid: str
    summary: str
    risk: float
    staged_at: float = field(default_factory=time.time)


@dataclass
class ContextCollapseSnapshot:
    staged: list[StagedCollapse] = field(default_factory=list)
    armed: bool = False
    last_spawn_tokens: int = 0


@dataclass
class ContextCollapseState:
    commits: list[CollapseCommit] = field(default_factory=list)
    snapshot: ContextCollapseSnapshot = field(default_factory=ContextCollapseSnapshot)
    pending_entries: list[StagedCollapse] = field(default_factory=list)
    _collapse_id_counter: int = 0
    _enabled: bool = False

    def next_collapse_id(self) -> str:
        self._collapse_id_counter += 1
        return format(self._collapse_id_counter, '016d')


_collapse_state: ContextCollapseState | None = None


def get_collapse_state() -> ContextCollapseState:
    global _collapse_state
    if _collapse_state is None:
        _collapse_state = ContextCollapseState()
    return _collapse_state


def init_contextCollapse() -> None:
    global _collapse_state
    _collapse_state = ContextCollapseState(_enabled=True)


def is_context_collapse_enabled() -> bool:
    state = get_collapse_state()
    return state._enabled


def reset_context_collapse() -> None:
    global _collapse_state
    _collapse_state = None


def should_commit_collapse(token_usage: int, context_window: int) -> bool:
    if not is_context_collapse_enabled():
        return False
    if context_window <= 0:
        return False
    ratio = token_usage / context_window
    return ratio >= COMMIT_THRESHOLD_RATIO


def should_block_collapse(token_usage: int, context_window: int) -> bool:
    if not is_context_collapse_enabled():
        return False
    if context_window <= 0:
        return False
    ratio = token_usage / context_window
    return ratio >= BLOCK_THRESHOLD_RATIO


def apply_collapse(
    messages: list[dict[str, Any]],
    collapse_state: ContextCollapseState,
) -> list[dict[str, Any]]:
    if not collapse_state.commits:
        return messages

    archived_uuids: set[str] = set()
    for commit in collapse_state.commits:
        in_span = False
        for msg in messages:
            msg_uuid = msg.get("uuid", "")
            if msg_uuid == commit.first_archived_uuid:
                in_span = True
            if in_span:
                archived_uuids.add(msg_uuid)
            if msg_uuid == commit.last_archived_uuid:
                in_span = False

    result = []
    inserted_summaries: set[str] = set()

    for msg in messages:
        msg_uuid = msg.get("uuid", "")

        for commit in collapse_state.commits:
            if (
                commit.summary_uuid == msg_uuid
                and commit.summary_uuid not in inserted_summaries
            ):
                result.append({
                    "type": msg.get("type", "user"),
                    "role": msg.get("role", "user"),
                    "content": commit.summary_content,
                    "uuid": commit.summary_uuid,
                    "parent_uuid": msg.get("parent_uuid"),
                    "_is_collapse_summary": True,
                })
                inserted_summaries.add(commit.summary_uuid)
                break
        else:
            if msg_uuid not in archived_uuids:
                result.append(msg)

    return result


def drain_collapses(collapse_state: ContextCollapseState) -> int:
    if not collapse_state.pending_entries:
        return 0

    committed = 0
    for staged in collapse_state.pending_entries:
        collapse_id = collapse_state.next_collapse_id()
        commit = CollapseCommit(
            collapse_id=collapse_id,
            summary_uuid=staged.start_uuid,
            summary_content=f'<collapsed id="{collapse_id}">{staged.summary}</collapsed>',
            summary=staged.summary,
            first_archived_uuid=staged.start_uuid,
            last_archived_uuid=staged.end_uuid,
        )
        collapse_state.commits.append(commit)
        committed += 1

    collapse_state.pending_entries.clear()
    return committed


def recover_from_overflow(
    messages: list[dict[str, Any]],
    token_usage: int,
    context_window: int,
) -> dict[str, Any]:
    state = get_collapse_state()
    committed = drain_collapses(state)

    if committed > 0:
        return {
            "messages": apply_collapse(messages, state),
            "committed": committed,
        }

    return {
        "messages": messages,
        "committed": 0,
    }


def apply_collapses_if_needed(
    messages: list[dict[str, Any]],
    token_usage: int,
    context_window: int,
) -> list[dict[str, Any]]:
    state = get_collapse_state()

    if should_commit_collapse(token_usage, context_window):
        drain_collapses(state)

    if state.commits:
        return apply_collapse(messages, state)

    return messages


def is_withheld_prompt_to_long(
    message: Any,
    is_prompt_too_long: bool,
    query_source: str = "",
) -> bool:
    if not is_context_collapse_enabled():
        return False
    if not is_prompt_too_long:
        return False
    if query_source in ("session_memory", "compact", "marble_origami"):
        return False
    return True


def save_collapse_state() -> dict[str, Any]:
    state = get_collapse_state()
    return {
        "commits": [
            {
                "collapse_id": c.collapse_id,
                "summary_uuid": c.summary_uuid,
                "summary_content": c.summary_content,
                "summary": c.summary,
                "first_archived_uuid": c.first_archived_uuid,
                "last_archived_uuid": c.last_archived_uuid,
            }
            for c in state.commits
        ],
        "snapshot": {
            "staged": [
                {
                    "start_uuid": s.start_uuid,
                    "end_uuid": s.end_uuid,
                    "summary": s.summary,
                    "risk": s.risk,
                    "staged_at": s.staged_at,
                }
                for s in state.snapshot.staged
            ],
            "armed": state.snapshot.armed,
            "last_spawn_tokens": state.snapshot.last_spawn_tokens,
        },
        "collapse_id_counter": state._collapse_id_counter,
        "enabled": state._enabled,
    }


def load_collapse_state(data: dict[str, Any]) -> None:
    global _collapse_state

    commits = []
    for c in data.get("commits", []):
        commits.append(CollapseCommit(
            collapse_id=c["collapse_id"],
            summary_uuid=c["summary_uuid"],
            summary_content=c["summary_content"],
            summary=c["summary"],
            first_archived_uuid=c["first_archived_uuid"],
            last_archived_uuid=c["last_archived_uuid"],
        ))

    snapshot_data = data.get("snapshot", {})
    staged = []
    for s in snapshot_data.get("staged", []):
        staged.append(StagedCollapse(
            start_uuid=s["start_uuid"],
            end_uuid=s["end_uuid"],
            summary=s["summary"],
            risk=s["risk"],
            staged_at=s.get("staged_at", time.time()),
        ))

    snapshot = ContextCollapseSnapshot(
        staged=staged,
        armed=snapshot_data.get("armed", False),
        last_spawn_tokens=snapshot_data.get("last_spawn_tokens", 0),
    )

    _collapse_state = ContextCollapseState(
        commits=commits,
        snapshot=snapshot,
        _collapse_id_counter=data.get("collapse_id_counter", 0),
        _enabled=data.get("enabled", False),
    )


def restore_from_entries(
    commits: list[dict[str, Any]],
    snapshot: dict[str, Any] | None = None,
) -> None:
    global _collapse_state

    commit_objects = []
    for c in commits:
        commit_objects.append(CollapseCommit(
            collapse_id=c.get("collapse_id", ""),
            summary_uuid=c.get("summary_uuid", ""),
            summary_content=c.get("summary_content", ""),
            summary=c.get("summary", ""),
            first_archived_uuid=c.get("first_archived_uuid", ""),
            last_archived_uuid=c.get("last_archived_uuid", ""),
        ))

    snap = ContextCollapseSnapshot()
    if snapshot:
        staged = []
        for s in snapshot.get("staged", []):
            staged.append(StagedCollapse(
                start_uuid=s.get("start_uuid", ""),
                end_uuid=s.get("end_uuid", ""),
                summary=s.get("summary", ""),
                risk=s.get("risk", 0.0),
                staged_at=s.get("staged_at", time.time()),
            ))
        snap = ContextCollapseSnapshot(
            staged=staged,
            armed=snapshot.get("armed", False),
            last_spawn_tokens=snapshot.get("last_spawn_tokens", 0),
        )

    _collapse_state = ContextCollapseState(
        commits=commit_objects,
        snapshot=snap,
        _enabled=True,
    )


def get_stats() -> dict[str, Any]:
    state = get_collapse_state()
    return {
        "collapsed_spans": len(state.commits),
        "staged_spans": len(state.pending_entries) + len(state.snapshot.staged),
        "collapsed_messages": sum(
            1 for c in state.commits for msg in [] if c.first_archived_uuid
        ),
        "enabled": state._enabled,
        "health": {
            "total_errors": 0,
        },
    }
