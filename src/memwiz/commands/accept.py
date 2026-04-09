from __future__ import annotations

import argparse
import sys

from memwiz.clock import CommandClock, build_command_clock
from memwiz.models import Decision, MemoryRecord
from memwiz.policy import RETAIN_THRESHOLD
from memwiz.scoring import contains_secret_like_content
from memwiz.serde import read_record
from memwiz.storage import write_workspace_canon

from memwiz.commands.score import (
    build_score_reasons,
    duplicate_flags,
    evaluate_workspace_record,
    score_workspace_record,
    workspace_candidate_path,
    _load_workspace_canon,
)


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
        print("Only captured workspace records can be accepted.", file=sys.stderr)
        return 1

    if contains_secret_like_content(
        record.summary,
        record.details or "",
        *(record.tags or []),
        *(item.ref for item in record.evidence),
        *(item.note for item in record.evidence if item.note),
    ):
        print("Accept rejected: secret-like content detected.", file=sys.stderr)
        return 4

    canon_records = _load_workspace_canon(args.config)
    has_strong_duplicate, has_near_duplicate = duplicate_flags(record, canon_records)
    result = evaluate_workspace_record(
        record,
        has_strong_duplicate=has_strong_duplicate,
        has_near_duplicate=has_near_duplicate,
    )

    timestamp = clock.timestamp()
    scored_record = score_workspace_record(
        record,
        canon_records=canon_records,
        timestamp=timestamp,
    )

    if result.disqualifiers or result.total < RETAIN_THRESHOLD:
        print(
            f"Accept rejected for {record.id}: {'; '.join(build_score_reasons(result))}",
            file=sys.stderr,
        )
        return 4

    accepted = _apply_acceptance(scored_record, timestamp)
    write_workspace_canon(args.config, accepted)
    record_path.unlink()
    print(f"Accepted {accepted.id} into workspace canon")
    return 0


def _apply_acceptance(record: MemoryRecord, timestamp: str) -> MemoryRecord:
    payload = record.to_dict()
    payload["status"] = "accepted"
    payload["decision"] = Decision(accepted_at=timestamp).to_dict()
    payload["updated_at"] = timestamp
    return MemoryRecord.from_dict(payload)
