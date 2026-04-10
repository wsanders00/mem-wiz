from __future__ import annotations

from pathlib import Path
from typing import Any

from memwiz.auditlog import read_audit_events
from memwiz.autonomy_policy import load_policy
from memwiz.compiler import build_digest_plans
from memwiz.doctoring import run_doctor
from memwiz.models import MemoryRecord
from memwiz.promotion import promotion_candidate_payload
from memwiz.serde import read_record
from memwiz.storage import list_global_records, list_workspace_records


STATUS_REVIEW_LIMIT = 5


def build_status_payload(config) -> dict[str, Any]:
    workspace_inbox_paths = list_workspace_records(config, "inbox")
    workspace_canon_paths = list_workspace_records(config, "canon")
    workspace_archive = list_workspace_records(config, "archive")
    global_canon_paths = list_global_records(config, "canon")
    global_archive = list_global_records(config, "archive")
    workspace_inbox = [read_record(path) for path in workspace_inbox_paths]
    workspace_canon = [read_record(path) for path in workspace_canon_paths]
    global_canon = [read_record(path) for path in global_canon_paths]
    audit_events = load_audit_events(config)
    doctor_findings = run_doctor(config)
    policy = load_policy(config)
    review_queue = _build_review_queue(workspace_inbox, audit_events)
    promotion_candidates = _build_promotion_candidates(workspace_canon, global_canon)

    return {
        "root": str(config.root),
        "workspace": config.workspace_slug,
        "policy_profile": policy.autonomy_profile,
        "counts": {
            "workspace_inbox": len(workspace_inbox_paths),
            "workspace_canon": len(workspace_canon_paths),
            "workspace_archive": len(workspace_archive),
            "global_canon": len(global_canon_paths),
            "global_archive": len(global_archive),
            "recent_audit_events": len(audit_events),
        },
        "digest_paths": {
            "workspace": str(config.workspace_cache / "digest.md"),
            "global": str(config.global_cache / "digest.md"),
        },
        "latest_timestamps": {
            "workspace_canon": _latest_record_timestamp(workspace_canon),
            "global_canon": _latest_record_timestamp(global_canon),
            "audit": audit_events[-1]["timestamp"] if audit_events else None,
        },
        "issue_counters": {
            "doctor_error": sum(1 for finding in doctor_findings if finding.level == "error"),
            "doctor_warn": sum(1 for finding in doctor_findings if finding.level == "warn"),
        },
        "review_required_count": len(workspace_inbox),
        "review_queue_count": len(review_queue),
        "review_queue": review_queue[:STATUS_REVIEW_LIMIT],
        "promotion_candidate_count": len(promotion_candidates),
        "promotion_candidates": promotion_candidates[:STATUS_REVIEW_LIMIT],
    }


def load_audit_events(
    config,
    *,
    workspace: str | None = None,
    day: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    outcome: str | None = None,
    needs_user: bool | None = None,
    reason_code: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return read_audit_events(
        config,
        workspace=config.workspace_slug if workspace is None else workspace,
        day=day,
        date_from=date_from,
        date_to=date_to,
        outcome=outcome,
        needs_user=needs_user,
        reason_code=reason_code,
        limit=limit,
    )


def build_context_payload(
    config,
    *,
    scope: str,
    generated_at: str,
) -> dict[str, Any]:
    plans = build_digest_plans(
        config,
        scope=scope,
        generated_at=generated_at,
    )
    text_parts = [_context_text_for_plan(plan) for plan in plans]

    if len(text_parts) == 1:
        text = text_parts[0]
    elif text_parts:
        text = "\n\n".join(part.rstrip("\n") for part in text_parts) + "\n"
    else:
        text = ""

    return {
        "scope": scope,
        "generated_at": generated_at,
        "included_record_ids": [
            record_id
            for plan in plans
            for record_id in plan.included_record_ids
        ],
        "omitted_count": sum(plan.omitted_count for plan in plans),
        "text": text,
    }


def _latest_record_timestamp(records: list[MemoryRecord]) -> str | None:
    timestamps = [record.updated_at for record in records]

    if not timestamps:
        return None

    return max(timestamps)


def _context_text_for_plan(plan) -> str:
    if plan.path.exists():
        return plan.path.read_text(encoding="utf-8")

    return plan.content


def _build_review_queue(
    inbox_records: list[MemoryRecord],
    audit_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest_event_by_memory_id: dict[str, dict[str, Any]] = {}

    for event in audit_events:
        memory_id = event.get("memory_id")
        if isinstance(memory_id, str):
            latest_event_by_memory_id[memory_id] = event

    queue: list[dict[str, Any]] = []
    for record in sorted(inbox_records, key=lambda item: (item.updated_at, item.id), reverse=True):
        latest_event = latest_event_by_memory_id.get(record.id, {})
        queue.append(
            {
                "memory_id": record.id,
                "kind": record.kind,
                "summary": record.summary,
                "updated_at": record.updated_at,
                "reason_codes": list(latest_event.get("reason_codes", [])),
                "needs_user": bool(latest_event.get("needs_user", False)),
            }
        )

    return queue


def _build_promotion_candidates(
    workspace_canon: list[MemoryRecord],
    global_canon: list[MemoryRecord],
) -> list[dict[str, Any]]:
    candidates = [
        candidate
        for record in workspace_canon
        for candidate in [promotion_candidate_payload(record, global_canon=global_canon)]
        if candidate is not None
    ]
    return sorted(
        candidates,
        key=lambda item: (-float(item["promote_score"]), item["memory_id"]),
    )
