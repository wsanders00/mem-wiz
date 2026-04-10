from __future__ import annotations

import argparse
from secrets import token_hex
import sys

from memwiz.clock import CommandClock, build_command_clock
from memwiz.models import Decision, MemoryRecord, Provenance, Score
from memwiz.scoring import ScoreResult, contains_secret_like_content, evaluate_record, is_promotion_eligible
from memwiz.serde import read_record
from memwiz.storage import workspace_record_path, write_global_canon

from memwiz.commands.score import build_score_reasons
from memwiz.promotion import (
    evaluate_workspace_promotion,
    load_global_canon_records,
    promotion_reason,
    promotion_rejection_reasons,
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)


def run(args: argparse.Namespace, *, command_clock: CommandClock | None = None) -> int:
    clock = command_clock or build_command_clock()

    try:
        record_path = workspace_record_path(args.config, "canon", args.id)
    except ValueError:
        print(f"Invalid memory id: {args.id}", file=sys.stderr)
        return 2

    if not record_path.exists():
        print(f"Accepted workspace record not found: {args.id}", file=sys.stderr)
        return 3

    record = read_record(record_path)

    if record.status != "accepted" or record.scope != "workspace":
        print("Only accepted workspace records can be promoted.", file=sys.stderr)
        return 1

    if contains_secret_like_content(
        record.summary,
        record.details or "",
        *(record.tags or []),
        *(item.ref for item in record.evidence),
        *(item.note for item in record.evidence if item.note),
    ):
        print("Promote rejected: secret-like content detected.", file=sys.stderr)
        return 4

    timestamp = clock.timestamp()
    evaluation = evaluate_workspace_promotion(
        record,
        global_canon=load_global_canon_records(args.config),
        timestamp=timestamp,
    )

    if not is_promotion_eligible(evaluation.result):
        print(
            f"Promote rejected for {record.id}: {'; '.join(promotion_rejection_reasons(evaluation.result))}",
            file=sys.stderr,
        )
        return 4

    retain_result = evaluate_record(
        evaluation.provisional,
        target_scope="global",
        has_strong_duplicate=evaluation.has_strong_duplicate,
        has_near_duplicate=evaluation.has_near_duplicate,
    )
    promoted = _finalize_promoted_record(
        record,
        timestamp=timestamp,
        retain_result=retain_result,
        promote_result=evaluation.result,
    )
    write_global_canon(args.config, promoted)
    print(f"Promoted {record.id} into global canon as {promoted.id}")
    return 0


def _finalize_promoted_record(
    record: MemoryRecord,
    *,
    timestamp: str,
    retain_result: ScoreResult,
    promote_result: ScoreResult,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=2,
        id=_build_memory_id(timestamp),
        scope="global",
        workspace=None,
        kind=record.kind,
        summary=record.summary,
        details=record.details,
        confidence=record.confidence,
        evidence=record.evidence,
        score=Score(
            reuse=retain_result.factors.reuse,
            specificity=retain_result.factors.specificity,
            durability=retain_result.factors.durability,
            evidence=retain_result.factors.evidence,
            novelty=retain_result.factors.novelty,
            scope_fit=retain_result.factors.scope_fit,
            retain=retain_result.total,
            promote=promote_result.total,
        ),
        tags=record.tags,
        status="accepted",
        decision=Decision(
            accepted_at=timestamp,
            accepted_mode="manual",
        ),
        origin=record.origin,
        score_reasons=build_score_reasons(retain_result),
        provenance=Provenance(
            source_scope="workspace",
            source_workspace=record.workspace or "",
            source_memory_id=record.id,
            promoted_at=timestamp,
            promotion_reason=promotion_reason(promote_result),
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )


def _build_memory_id(timestamp: str) -> str:
    return f"mem_{timestamp[:10].replace('-', '')}_{token_hex(4)}"
