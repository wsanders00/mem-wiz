from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from memwiz.clock import CommandClock
from memwiz.config import MemwizConfig
from memwiz.dedupe import is_strong_duplicate, resolve_supersedes, select_duplicate_winner
from memwiz.models import MemoryRecord
from memwiz.retrieval import CanonDecodeError, CanonValidationError
from memwiz.serde import read_record
from memwiz.storage import (
    archive_global_record,
    archive_workspace_record,
    list_global_records,
    list_workspace_records,
)


@dataclass(frozen=True)
class PruneAction:
    record: MemoryRecord
    scope: str
    workspace_label: str
    reason: str


@dataclass(frozen=True)
class _ScopedRecord:
    record: MemoryRecord
    scope: str
    workspace_label: str


def plan_prune(config: MemwizConfig, *, scope: str) -> list[PruneAction]:
    normalized_scope = _validate_scope(scope)
    scoped_records = _load_scoped_records(config, normalized_scope)
    records = [item.record for item in scoped_records]

    superseded_actions = _plan_supersede_actions(scoped_records, records)
    duplicate_actions = _plan_duplicate_actions(
        scoped_records,
        excluded_keys=set(superseded_actions),
    )

    combined_actions = {**superseded_actions, **duplicate_actions}
    return sorted(combined_actions.values(), key=_action_sort_key)


def apply_prune_plan(
    config: MemwizConfig,
    actions: list[PruneAction],
    *,
    command_clock: CommandClock,
) -> list[PruneAction]:
    applied: list[PruneAction] = []

    for action in actions:
        if action.scope == "workspace":
            archive_workspace_record(
                config,
                action.record.id,
                archive_reason=action.reason,
                command_clock=command_clock,
            )
        elif action.scope == "global":
            archive_global_record(
                config,
                action.record.id,
                archive_reason=action.reason,
                command_clock=command_clock,
            )
        else:
            raise ValueError(f"invalid prune action scope: {action.scope}")

        applied.append(action)

    return applied


def _validate_scope(scope: str) -> str:
    if scope not in {"workspace", "global", "all"}:
        raise ValueError(f"invalid prune scope: {scope}")

    return scope


def _load_scoped_records(config: MemwizConfig, scope: str) -> list[_ScopedRecord]:
    scoped_records: list[_ScopedRecord] = []

    if scope in {"workspace", "all"}:
        scoped_records.extend(
            _load_records_for_paths(
                list_workspace_records(config, "canon"),
                expected_scope="workspace",
                workspace_label=config.workspace_slug,
                expected_workspace=config.workspace_slug,
            )
        )

    if scope in {"global", "all"}:
        scoped_records.extend(
            _load_records_for_paths(
                list_global_records(config, "canon"),
                expected_scope="global",
                workspace_label="-",
                expected_workspace=None,
            )
        )

    return scoped_records


def _load_records_for_paths(
    paths: list[Path],
    *,
    expected_scope: str,
    workspace_label: str,
    expected_workspace: str | None,
) -> list[_ScopedRecord]:
    return [
        _ScopedRecord(
            record=_load_canon_record(
                path,
                expected_scope=expected_scope,
                expected_workspace=expected_workspace,
            ),
            scope=expected_scope,
            workspace_label=workspace_label,
        )
        for path in paths
    ]


def _load_canon_record(
    path: Path,
    *,
    expected_scope: str,
    expected_workspace: str | None,
) -> MemoryRecord:
    try:
        record = read_record(path)
    except yaml.YAMLError as exc:
        raise CanonDecodeError(path, str(exc)) from exc
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanonValidationError(path, str(exc)) from exc

    if record.status != "accepted":
        raise CanonValidationError(path, f"canon record must be accepted, got {record.status}")

    if record.scope != expected_scope:
        raise CanonValidationError(
            path,
            f"canon record scope must be {expected_scope}, got {record.scope}",
        )

    if expected_scope == "workspace" and record.workspace != expected_workspace:
        raise CanonValidationError(
            path,
            (
                "workspace canon record must belong to "
                f"{expected_workspace}, got {record.workspace}"
            ),
        )

    return record


def _plan_supersede_actions(
    scoped_records: list[_ScopedRecord],
    snapshot: list[MemoryRecord],
) -> dict[tuple[str, str], PruneAction]:
    scoped_lookup = {(item.record.id, item.scope): item for item in scoped_records}
    successors_by_target: dict[tuple[str, str], list[str]] = {}

    for item in scoped_records:
        resolved = resolve_supersedes(item.record, snapshot)
        if resolved is None:
            continue

        target_key = (resolved.id, resolved.scope)
        successors_by_target.setdefault(target_key, []).append(item.record.id)

    actions: dict[tuple[str, str], PruneAction] = {}
    for target_key, successors in successors_by_target.items():
        target = scoped_lookup[target_key]
        smallest_successor_id = min(successors)
        actions[target_key] = PruneAction(
            record=target.record,
            scope=target.scope,
            workspace_label=target.workspace_label,
            reason=f"superseded-by:{smallest_successor_id}",
        )

    return actions


def _plan_duplicate_actions(
    scoped_records: list[_ScopedRecord],
    *,
    excluded_keys: set[tuple[str, str]],
) -> dict[tuple[str, str], PruneAction]:
    remaining = {
        (item.record.id, item.scope): item
        for item in scoped_records
        if (item.record.id, item.scope) not in excluded_keys
    }
    actions: dict[tuple[str, str], PruneAction] = {}

    while remaining:
        winner = select_duplicate_winner(
            [item.record for item in remaining.values()]
        )
        winner_key = (winner.id, winner.scope)
        losers = [
            item
            for key, item in remaining.items()
            if key != winner_key and is_strong_duplicate(winner, item.record)
        ]

        remaining.pop(winner_key)

        for loser in losers:
            loser_key = (loser.record.id, loser.scope)
            actions[loser_key] = PruneAction(
                record=loser.record,
                scope=loser.scope,
                workspace_label=loser.workspace_label,
                reason=f"strong-duplicate-of:{winner.id}",
            )
            remaining.pop(loser_key, None)

    return actions


def _action_sort_key(action: PruneAction) -> tuple[int, str]:
    return (
        0 if action.scope == "workspace" else 1,
        action.record.id,
    )
