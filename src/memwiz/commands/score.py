from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Iterable

from memwiz.clock import CommandClock, build_command_clock
from memwiz.dedupe import is_near_duplicate, is_strong_duplicate
from memwiz.models import MemoryRecord, Score, normalize_memory_id
from memwiz.scoring import ScoreResult, evaluate_record
from memwiz.serde import read_record, write_record
from memwiz.storage import list_workspace_records


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)


def run(args: argparse.Namespace, *, command_clock: CommandClock | None = None) -> int:
    clock = command_clock or build_command_clock()
    record_path = workspace_candidate_path(args.config, args.id)

    if not record_path.exists():
        print(f"Workspace candidate not found: {args.id}", file=sys.stderr)
        return 3

    record = read_record(record_path)

    if record.status != "captured":
        print("Only captured workspace records can be scored.", file=sys.stderr)
        return 1

    scored_record = score_workspace_record(
        record,
        canon_records=_load_workspace_canon(args.config),
        timestamp=clock.timestamp(),
    )
    write_record(record_path, scored_record)
    print(f"Scored {scored_record.id} with retain={scored_record.score.retain:.2f}")
    return 0


def workspace_candidate_path(config, record_id: str) -> Path:
    normalized = normalize_memory_id(record_id)
    return config.workspace_inbox / f"{normalized}.yaml"


def _load_workspace_canon(config) -> list[MemoryRecord]:
    return [read_record(path) for path in list_workspace_records(config, "canon")]


def duplicate_flags(
    record: MemoryRecord,
    canon_records: Iterable[MemoryRecord],
) -> tuple[bool, bool]:
    canon_list = list(canon_records)
    has_strong_duplicate = any(
        is_strong_duplicate(record, candidate)
        for candidate in canon_list
        if candidate.id != record.id
    )
    has_near_duplicate = any(
        is_near_duplicate(record, candidate)
        for candidate in canon_list
        if candidate.id != record.id
    )
    return has_strong_duplicate, has_near_duplicate


def evaluate_workspace_record(
    record: MemoryRecord,
    *,
    has_strong_duplicate: bool = False,
    has_near_duplicate: bool = False,
) -> ScoreResult:
    return evaluate_record(
        record,
        target_scope="workspace",
        has_strong_duplicate=has_strong_duplicate,
        has_near_duplicate=has_near_duplicate,
    )


def _apply_score(
    record: MemoryRecord,
    result: ScoreResult,
    timestamp: str,
) -> MemoryRecord:
    score = Score(
        reuse=result.factors.reuse,
        specificity=result.factors.specificity,
        durability=result.factors.durability,
        evidence=result.factors.evidence,
        novelty=result.factors.novelty,
        scope_fit=result.factors.scope_fit,
        retain=result.total,
    )
    payload = record.to_dict()
    payload["score"] = score.to_dict()
    payload["score_reasons"] = list(build_score_reasons(result))
    payload["updated_at"] = timestamp
    return MemoryRecord.from_dict(payload)


def score_workspace_record(
    record: MemoryRecord,
    *,
    canon_records: Iterable[MemoryRecord],
    timestamp: str,
) -> MemoryRecord:
    has_strong_duplicate, has_near_duplicate = duplicate_flags(record, canon_records)
    result = evaluate_workspace_record(
        record,
        has_strong_duplicate=has_strong_duplicate,
        has_near_duplicate=has_near_duplicate,
    )
    return _apply_score(record, result, timestamp)


def build_score_reasons(result: ScoreResult) -> tuple[str, ...]:
    if result.disqualifiers:
        return tuple(result.disqualifiers)

    reasons: list[str] = []

    if result.factors.reuse >= 0.75:
        reasons.append("likely reusable")
    if result.factors.evidence >= 0.75:
        reasons.append("supported by evidence")
    if result.factors.durability >= 0.75:
        reasons.append("durable enough to retain")
    if result.factors.novelty >= 0.75:
        reasons.append("adds new value beyond active canon")

    if not reasons:
        reasons.append(f"retain-score:{result.total:.2f}")

    return tuple(reasons)
