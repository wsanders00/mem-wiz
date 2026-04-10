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
    load_workspace_canon,
    score_workspace_candidate,
    workspace_candidate_path,
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)


def run(args: argparse.Namespace, *, command_clock: CommandClock | None = None) -> int:
    clock = command_clock or build_command_clock()
    try:
        record_path = workspace_candidate_path(args.config, args.id)
    except ValueError:
        print(f"Invalid memory id: {args.id}", file=sys.stderr)
        return 2

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

    timestamp = clock.timestamp()
    canon_records = load_workspace_canon(args.config)
    scored_record, result, _, _ = score_workspace_candidate(
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

    accepted = apply_manual_acceptance(scored_record, timestamp)
    write_workspace_canon(args.config, accepted)
    record_path.unlink()
    print(f"Accepted {accepted.id} into workspace canon")
    return 0


def apply_manual_acceptance(record: MemoryRecord, timestamp: str) -> MemoryRecord:
    return apply_acceptance(
        record,
        timestamp=timestamp,
        accepted_mode="manual",
        accepted_by=None,
    )


def apply_policy_acceptance(
    record: MemoryRecord,
    *,
    timestamp: str,
    accepted_by: str,
) -> MemoryRecord:
    return apply_acceptance(
        record,
        timestamp=timestamp,
        accepted_mode="policy",
        accepted_by=accepted_by,
    )


def apply_acceptance(
    record: MemoryRecord,
    *,
    timestamp: str,
    accepted_mode: str,
    accepted_by: str | None,
) -> MemoryRecord:
    payload = record.to_dict()
    payload["schema_version"] = 2
    payload["status"] = "accepted"
    payload["decision"] = Decision(
        accepted_at=timestamp,
        accepted_mode=accepted_mode,
        accepted_by=accepted_by,
    ).to_dict()
    payload["updated_at"] = timestamp
    return MemoryRecord.from_dict(payload)
