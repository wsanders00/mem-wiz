from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memwiz.commands.score import build_score_reasons
from memwiz.dedupe import is_near_duplicate, is_strong_duplicate
from memwiz.models import Decision, MemoryRecord, Provenance
from memwiz.policy import (
    GLOBAL_PROMOTION_MIN_DURABILITY,
    GLOBAL_PROMOTION_MIN_EVIDENCE,
    PROMOTE_THRESHOLD,
)
from memwiz.scoring import (
    ScoreResult,
    contains_secret_like_content,
    evaluate_record,
    is_promotion_eligible,
)
from memwiz.serde import read_record
from memwiz.storage import list_global_records


@dataclass(frozen=True)
class PromotionEvaluation:
    provisional: MemoryRecord
    result: ScoreResult
    has_strong_duplicate: bool
    has_near_duplicate: bool


def load_global_canon_records(config) -> list[MemoryRecord]:
    return [read_record(path) for path in list_global_records(config, "canon")]


def promotion_duplicate_flags(
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


def build_provisional_global_record(record: MemoryRecord, timestamp: str) -> MemoryRecord:
    payload = record.to_dict()
    score_payload = record.score.to_dict() if record.score is not None else {}
    score_payload["promote"] = score_payload.get("retain", 0.0)
    payload["schema_version"] = 2
    payload["id"] = record.id
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


def evaluate_workspace_promotion(
    record: MemoryRecord,
    *,
    global_canon: list[MemoryRecord],
    timestamp: str,
) -> PromotionEvaluation:
    provisional = build_provisional_global_record(record, timestamp)
    has_strong_duplicate, has_near_duplicate = promotion_duplicate_flags(
        provisional,
        global_canon,
    )
    result = evaluate_record(
        record,
        target_scope="global",
        has_strong_duplicate=has_strong_duplicate,
        has_near_duplicate=has_near_duplicate,
    )
    return PromotionEvaluation(
        provisional=provisional,
        result=result,
        has_strong_duplicate=has_strong_duplicate,
        has_near_duplicate=has_near_duplicate,
    )


def promotion_rejection_reasons(result: ScoreResult) -> tuple[str, ...]:
    reasons = list(build_score_reasons(result))

    if result.total < PROMOTE_THRESHOLD:
        reasons.append(f"promote-score:{result.total:.2f}")

    if result.factors.durability < GLOBAL_PROMOTION_MIN_DURABILITY:
        reasons.append(f"durability:{result.factors.durability:.2f}")

    if result.factors.evidence < GLOBAL_PROMOTION_MIN_EVIDENCE:
        reasons.append(f"evidence:{result.factors.evidence:.2f}")

    return tuple(dict.fromkeys(reasons))


def promotion_reason(result: ScoreResult) -> str:
    reasons = list(build_score_reasons(result))
    reasons.append(f"promote-score:{result.total:.2f}")
    return "; ".join(dict.fromkeys(reasons))


def promotion_candidate_payload(
    record: MemoryRecord,
    *,
    global_canon: list[MemoryRecord],
) -> dict[str, Any] | None:
    if record.scope != "workspace" or record.status != "accepted":
        return None

    if contains_secret_like_content(
        record.summary,
        record.details or "",
        *(record.tags or []),
        *(item.ref for item in record.evidence),
        *(item.note for item in record.evidence if item.note),
    ):
        return None

    evaluation = evaluate_workspace_promotion(
        record,
        global_canon=global_canon,
        timestamp=record.updated_at,
    )

    if not is_promotion_eligible(evaluation.result):
        return None

    return {
        "memory_id": record.id,
        "kind": record.kind,
        "summary": record.summary,
        "promote_score": evaluation.result.total,
        "promotion_reason": promotion_reason(evaluation.result),
    }
