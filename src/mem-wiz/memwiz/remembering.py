from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from typing import Any, Sequence

from memwiz.auditlog import append_audit_event
from memwiz.autonomy_policy import (
    AutonomyPolicy,
    kind_allows_auto_accept,
    profile_allows_auto_accept,
    resolve_policy,
)
from memwiz.clock import CommandClock, build_command_clock
from memwiz.commands.accept import apply_policy_acceptance
from memwiz.commands.score import duplicate_flags, load_workspace_canon, score_workspace_candidate
from memwiz.models import EvidenceItem, MemoryRecord, Origin
from memwiz.policy import DISQUALIFIERS, RETAIN_THRESHOLD
from memwiz.scoring import contains_secret_like_content
from memwiz.serde import write_record
from memwiz.storage import write_workspace_candidate, write_workspace_canon


REASON_CODE_BY_DISQUALIFIER = {
    message: code
    for code, message in DISQUALIFIERS.items()
}


@dataclass(frozen=True)
class RememberResult:
    workspace: str
    memory_id: str
    outcome: str
    accepted: bool
    review_required: bool
    reason_codes: tuple[str, ...]
    score: dict[str, Any] | None
    audit_path: Path
    needs_user: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "memory_id": self.memory_id,
            "outcome": self.outcome,
            "accepted": self.accepted,
            "review_required": self.review_required,
            "reason_codes": list(self.reason_codes),
            "score": self.score,
            "audit_path": str(self.audit_path),
        }


def remember(
    config,
    *,
    kind: str,
    summary: str,
    details: str | None,
    tags: Sequence[str],
    evidence_source: str,
    evidence_ref: str,
    actor_name: str,
    policy_profile: str | None = None,
    command_clock: CommandClock | None = None,
) -> RememberResult:
    clock = command_clock or build_command_clock()
    timestamp = clock.timestamp()
    policy = resolve_policy(config, policy_profile=policy_profile)
    record = _build_record(
        config,
        kind=kind,
        summary=summary,
        details=details,
        tags=tags,
        evidence_source=evidence_source,
        evidence_ref=evidence_ref,
        actor_name=actor_name,
        timestamp=timestamp,
    )

    if contains_secret_like_content(
        summary,
        details or "",
        evidence_ref,
        *(tags or ()),
    ):
        return _audit_and_return(
            config,
            record=record,
            actor_name=actor_name,
            policy=policy,
            outcome="rejected_secret_like",
            accepted=False,
            review_required=False,
            reason_codes=("secret_like",),
            score_payload=None,
            needs_user=False,
            timestamp=timestamp,
        )

    canon_records = load_workspace_canon(config)
    has_strong_duplicate, has_near_duplicate = duplicate_flags(record, canon_records)

    if has_strong_duplicate:
        return _audit_and_return(
            config,
            record=record,
            actor_name=actor_name,
            policy=policy,
            outcome="skipped_duplicate",
            accepted=False,
            review_required=False,
            reason_codes=("strong_duplicate",),
            score_payload=None,
            needs_user=False,
            timestamp=timestamp,
        )

    candidate_path = write_workspace_candidate(config, record)
    scored_record, score_result, _, _ = score_workspace_candidate(
        record,
        canon_records=canon_records,
        timestamp=timestamp,
    )
    write_record(candidate_path, scored_record)
    score_payload = scored_record.score.to_dict() if scored_record.score is not None else None

    if _should_auto_accept(
        scored_record,
        policy=policy,
        has_near_duplicate=has_near_duplicate,
        score_total=score_result.total,
        disqualifiers=score_result.disqualifiers,
    ):
        accepted_record = apply_policy_acceptance(
            scored_record,
            timestamp=timestamp,
            accepted_by=policy.autonomy_profile,
        )
        write_workspace_canon(config, accepted_record)
        candidate_path.unlink()
        return _audit_and_return(
            config,
            record=accepted_record,
            actor_name=actor_name,
            policy=policy,
            outcome="auto_accepted",
            accepted=True,
            review_required=False,
            reason_codes=(),
            score_payload=score_payload,
            needs_user=False,
            timestamp=timestamp,
        )

    outcome, review_required, reason_codes, needs_user = _review_outcome(
        record=scored_record,
        policy=policy,
        has_near_duplicate=has_near_duplicate,
        score_total=score_result.total,
        disqualifiers=score_result.disqualifiers,
    )
    return _audit_and_return(
        config,
        record=scored_record,
        actor_name=actor_name,
        policy=policy,
        outcome=outcome,
        accepted=False,
        review_required=review_required,
        reason_codes=reason_codes,
        score_payload=score_payload,
        needs_user=needs_user,
        timestamp=timestamp,
    )


def _build_record(
    config,
    *,
    kind: str,
    summary: str,
    details: str | None,
    tags: Sequence[str],
    evidence_source: str,
    evidence_ref: str,
    actor_name: str,
    timestamp: str,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=2,
        id=_build_memory_id(timestamp),
        scope="workspace",
        workspace=config.workspace_slug,
        kind=kind,
        summary=summary,
        details=details,
        evidence=[EvidenceItem(source=evidence_source, ref=evidence_ref)],
        status="captured",
        origin=Origin(
            actor_type="agent",
            actor_name=actor_name,
            capture_mode="autonomous",
        ),
        tags=tags,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _build_memory_id(timestamp: str) -> str:
    date_part = timestamp[:10].replace("-", "")
    return f"mem_{date_part}_{token_hex(4)}"


def _should_auto_accept(
    record: MemoryRecord,
    *,
    policy: AutonomyPolicy,
    has_near_duplicate: bool,
    score_total: float,
    disqualifiers: Sequence[str],
) -> bool:
    if not profile_allows_auto_accept(policy):
        return False

    if has_near_duplicate:
        return False

    if not kind_allows_auto_accept(policy, record.kind):
        return False

    if policy.require_non_agent_evidence and not _has_non_agent_evidence(record):
        return False

    if disqualifiers:
        return False

    return score_total >= RETAIN_THRESHOLD


def _review_outcome(
    *,
    record: MemoryRecord,
    policy: AutonomyPolicy,
    has_near_duplicate: bool,
    score_total: float,
    disqualifiers: Sequence[str],
) -> tuple[str, bool, tuple[str, ...], bool]:
    if not profile_allows_auto_accept(policy):
        return "captured_only", True, ("manual_profile",), True

    reason_codes: list[str] = []

    if has_near_duplicate:
        reason_codes.append("near_duplicate")

    if not kind_allows_auto_accept(policy, record.kind):
        reason_codes.append("kind_requires_review")

    if policy.require_non_agent_evidence and not _has_non_agent_evidence(record):
        reason_codes.append("requires_non_agent_evidence")

    for disqualifier in disqualifiers:
        reason_codes.append(REASON_CODE_BY_DISQUALIFIER.get(disqualifier, "scoring_disqualifier"))

    if score_total < RETAIN_THRESHOLD:
        reason_codes.append("score_below_retain_threshold")

    if not reason_codes:
        reason_codes.append("policy_review")

    return "review_required", True, tuple(dict.fromkeys(reason_codes)), True


def _has_non_agent_evidence(record: MemoryRecord) -> bool:
    return any(item.source != "agent" for item in record.evidence)


def _audit_and_return(
    config,
    *,
    record: MemoryRecord,
    actor_name: str,
    policy: AutonomyPolicy,
    outcome: str,
    accepted: bool,
    review_required: bool,
    reason_codes: Sequence[str],
    score_payload: dict[str, Any] | None,
    needs_user: bool,
    timestamp: str,
) -> RememberResult:
    audit_result = append_audit_event(
        config,
        {
            "timestamp": timestamp,
            "workspace": config.workspace_slug,
            "memory_id": record.id,
            "actor": {"type": "agent", "name": actor_name},
            "action": "remember",
            "outcome": outcome,
            "reason_codes": list(reason_codes),
            "score_snapshot": score_payload,
            "summary_preview": record.summary,
            "evidence_summary": [f"{item.source}:{item.ref}" for item in record.evidence],
            "policy_profile": policy.autonomy_profile,
            "needs_user": needs_user,
        },
    )

    return RememberResult(
        workspace=config.workspace_slug,
        memory_id=record.id,
        outcome=outcome,
        accepted=accepted,
        review_required=review_required,
        reason_codes=tuple(reason_codes),
        score=score_payload,
        audit_path=audit_result.path,
        needs_user=needs_user,
    )
