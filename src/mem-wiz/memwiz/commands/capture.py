from __future__ import annotations

import argparse
from secrets import token_hex
import sys

from memwiz.clock import CommandClock, build_command_clock
from memwiz.models import ALLOWED_EVIDENCE_SOURCES, ALLOWED_KINDS, EvidenceItem, MemoryRecord
from memwiz.scoring import contains_secret_like_content
from memwiz.storage import initialize_root, write_workspace_candidate


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kind", required=True, choices=sorted(ALLOWED_KINDS))
    parser.add_argument("--summary", required=True)
    parser.add_argument("--details")
    parser.add_argument("--tag", dest="tags", action="append", default=[])
    parser.add_argument(
        "--evidence-source",
        required=True,
        choices=sorted(ALLOWED_EVIDENCE_SOURCES),
    )
    parser.add_argument("--evidence-ref", required=True)


def run(args: argparse.Namespace, *, command_clock: CommandClock | None = None) -> int:
    if contains_secret_like_content(
        args.summary,
        args.details or "",
        args.evidence_ref,
        *(args.tags or []),
    ):
        print("Capture rejected: secret-like content detected.", file=sys.stderr)
        return 4

    clock = command_clock or build_command_clock()
    timestamp = clock.timestamp()
    record = MemoryRecord(
        schema_version=1,
        id=_build_memory_id(timestamp),
        scope="workspace",
        workspace=args.config.workspace_slug,
        kind=args.kind,
        summary=args.summary,
        details=args.details,
        evidence=[EvidenceItem(source=args.evidence_source, ref=args.evidence_ref)],
        status="captured",
        tags=args.tags,
        created_at=timestamp,
        updated_at=timestamp,
    )

    initialize_root(args.config)
    write_workspace_candidate(args.config, record)
    print(f"Captured {record.id}")
    return 0


def _build_memory_id(timestamp: str) -> str:
    date_part = timestamp[:10].replace("-", "")
    return f"mem_{date_part}_{token_hex(4)}"
