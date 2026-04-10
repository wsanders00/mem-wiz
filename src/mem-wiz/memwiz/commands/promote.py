from __future__ import annotations

import argparse
from secrets import token_hex
import sys

from memwiz.clock import CommandClock, build_command_clock
from memwiz.dedupe import is_near_duplicate, is_strong_duplicate
from memwiz.models import Decision, MemoryRecord, Provenance, Score
from memwiz.policy import (
    GLOBAL_PROMOTION_MIN_DURABILITY,
    GLOBAL_PROMOTION_MIN_EVIDENCE,
    PROMOTE_THRESHOLD,
)
from memwiz.scoring import ScoreResult, contains_secret_like_content, evaluate_record, is_promotion_eligible
from memwiz.serde import read_record
from memwiz.storage import list_global_records, workspace_record_path, write_global_canon

from memwiz.commands.score import build_score_reasons


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
    global_canon = _load_global_canon(args.config)
    provisional = _build_provisional_global_record(record, timestamp)
    has_strong_duplicate, has_near_duplicate = _duplicate_flags(provisional, global_canon)
    promote_result = evaluate_record(
        record,
        target_scope="global",
        has_strong_duplicate=has_strong_duplicate,
        has_near_duplicate=has_near_duplicate,
    )

    if not is_promotion_eligible(promote_result):
        print(
            f"Promote rejected for {record.id}: {'; '.join(_promotion_rejection_reasons(promote_result))}",
            file=sys.stderr,
        )
        return 4

    retain_result = evaluate_record(
        provisional,
        target_scope="global",
        has_strong_duplicate=has_strong_duplicate,
        has_near_duplicate=has_near_duplicate,
    )
    promoted = _finalize_promoted_record(
        record,
        timestamp=timestamp,
        retain_result=retain_result,
        promote_result=promote_result,
    )
    write_global_canon(args.config, promoted)
    print(f"Promoted {record.id} into global canon as {promoted.id}")
    return 0


def _load_global_canon(config) -> list[MemoryRecord]:
    return [read_record(path) for path in list_global_records(config, "canon")]


def _duplicate_flags(
    record: MemoryRecord,
    canon_records: list[MemoryRecord],
) -> tuple[bool, bool]:
    has_strong_duplicate = any(
        is_strong_duplicate(record, candidate)
        for candidate in canon_records
        if candidate.id != record.id
    )
    has_near_duplicate = any(
        is_near_duplicate(record, candidate)
        for candidate in canon_records
        if candidate.id != record.id
    )
    return has_strong_duplicate, has_near_duplicate


def _build_provisional_global_record(record: MemoryRecord, timestamp: str) -> MemoryRecord:
    payload = record.to_dict()
    payload["schema_version"] = 2
    score_payload = record.score.to_dict() if record.score is not None else {}
    score_payload["promote"] = score_payload.get("retain", 0.0)
    payload["id"] = _build_memory_id(timestamp)
    payload["scope"] = "global"
    payload.pop("workspace", None)
    payload["score"] = score_payload
    payload["decision"] = Decision(
        accepted_at=timestamp,
        accepted_mode="manual",
    ).to_dict()
    payload["provenance"] = Provenance(
        source_scope="workspace",
        source_workspace=record.workspace or "",
        source_memory_id=record.id,
        promoted_at=timestamp,
        promotion_reason="promotion eligibility pending",
    ).to_dict()
    payload["created_at"] = timestamp
    payload["updated_at"] = timestamp
    payload.pop("supersedes", None)
    return MemoryRecord.from_dict(payload)


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
            promotion_reason=_promotion_reason(promote_result),
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )


def _promotion_rejection_reasons(result: ScoreResult) -> tuple[str, ...]:
    reasons = list(build_score_reasons(result))

    if result.total < PROMOTE_THRESHOLD:
        reasons.append(f"promote-score:{result.total:.2f}")

    if result.factors.durability < GLOBAL_PROMOTION_MIN_DURABILITY:
        reasons.append(f"durability:{result.factors.durability:.2f}")

    if result.factors.evidence < GLOBAL_PROMOTION_MIN_EVIDENCE:
        reasons.append(f"evidence:{result.factors.evidence:.2f}")

    return tuple(dict.fromkeys(reasons))


def _promotion_reason(result: ScoreResult) -> str:
    reasons = list(build_score_reasons(result))
    reasons.append(f"promote-score:{result.total:.2f}")
    return "; ".join(dict.fromkeys(reasons))


def _build_memory_id(timestamp: str) -> str:
    return f"mem_{timestamp[:10].replace('-', '')}_{token_hex(4)}"
