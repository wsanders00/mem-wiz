from __future__ import annotations

import json
from pathlib import Path

from memwiz.auditlog import append_audit_event
from memwiz.config import build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Origin, Score
from memwiz.storage import write_workspace_candidate, write_workspace_canon


def test_status_json_reports_policy_and_workspace_counts(
    run_memwiz,
    tmp_path: Path,
) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260410_11111111",
            workspace=config.workspace_slug,
            summary="Workflow review guide",
        ),
    )

    result = run_memwiz(
        "status",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["policy_profile"] == "balanced"
    assert payload["workspace"] == "task-space"
    assert payload["counts"]["workspace_canon"] == 1
    assert payload["counts"]["workspace_inbox"] == 0
    assert payload["review_required_count"] == 0


def test_status_json_reports_review_queue_metadata(
    run_memwiz,
    tmp_path: Path,
) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
    record = captured_workspace_record(
        "mem_20260410_deadbeef",
        workspace=config.workspace_slug,
        summary="Run pytest before merge in this repository.",
    )
    write_workspace_candidate(config, record)
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T12:00:00Z",
            "workspace": config.workspace_slug,
            "memory_id": record.id,
            "actor": {"type": "agent", "name": "codex"},
            "action": "remember",
            "outcome": "review_required",
            "reason_codes": ["near_duplicate"],
            "score_snapshot": {"retain": 0.75},
            "summary_preview": record.summary,
            "evidence_summary": ["command:pytest -q"],
            "policy_profile": "balanced",
            "needs_user": True,
        },
    )

    result = run_memwiz(
        "status",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["review_required_count"] == 1
    assert payload["review_queue_count"] == 1
    assert payload["review_queue"][0]["memory_id"] == record.id
    assert payload["review_queue"][0]["reason_codes"] == ["near_duplicate"]
    assert payload["review_queue"][0]["needs_user"] is True


def test_status_json_reports_promotion_candidates(
    run_memwiz,
    tmp_path: Path,
) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
    record = accepted_workspace_record(
        "mem_20260410_11111111",
        workspace=config.workspace_slug,
        summary="Prefer concise contributor guidance across future repositories.",
    )
    write_workspace_canon(config, record)

    result = run_memwiz(
        "status",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["promotion_candidate_count"] == 1
    assert payload["promotion_candidates"][0]["memory_id"] == record.id
    assert payload["promotion_candidates"][0]["promote_score"] >= 0.78
    assert "promote-score:" in payload["promotion_candidates"][0]["promotion_reason"]


def test_status_text_reports_review_and_promotion_counts(
    run_memwiz,
    tmp_path: Path,
) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
    write_workspace_candidate(
        config,
        captured_workspace_record(
            "mem_20260410_deadbeef",
            workspace=config.workspace_slug,
            summary="Run pytest before merge in this repository.",
        ),
    )
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T12:00:00Z",
            "workspace": config.workspace_slug,
            "memory_id": "mem_20260410_deadbeef",
            "actor": {"type": "agent", "name": "codex"},
            "action": "remember",
            "outcome": "review_required",
            "reason_codes": ["near_duplicate"],
            "score_snapshot": {"retain": 0.75},
            "summary_preview": "Run pytest before merge in this repository.",
            "evidence_summary": ["command:pytest -q"],
            "policy_profile": "balanced",
            "needs_user": True,
        },
    )
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260410_11111111",
            workspace=config.workspace_slug,
            summary="Prefer concise contributor guidance across future repositories.",
        ),
    )

    result = run_memwiz(
        "status",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 0
    assert "review_queue_count\t1" in result.stdout
    assert "promotion_candidate_count\t1" in result.stdout


def accepted_workspace_record(
    record_id: str,
    *,
    workspace: str,
    summary: str,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=2,
        id=record_id,
        scope="workspace",
        workspace=workspace,
        kind="workflow",
        summary=summary,
        details="Durable workflow guidance for future sessions.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-10")],
        score=Score(
            reuse=0.75,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=1.0,
            scope_fit=1.0,
            retain=0.95,
        ),
        status="accepted",
        decision=Decision(
            accepted_at="2026-04-10T09:00:00Z",
            accepted_mode="manual",
        ),
        score_reasons=["durable enough to retain"],
        created_at="2026-04-10T09:00:00Z",
        updated_at="2026-04-10T09:00:00Z",
    )


def captured_workspace_record(
    record_id: str,
    *,
    workspace: str,
    summary: str,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=2,
        id=record_id,
        scope="workspace",
        workspace=workspace,
        kind="workflow",
        summary=summary,
        details="Needs a quick human review before reuse.",
        evidence=[EvidenceItem(source="command", ref="pytest -q")],
        score=Score(
            reuse=0.75,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=0.25,
            scope_fit=1.0,
            retain=0.80,
        ),
        status="captured",
        origin=Origin(
            actor_type="agent",
            actor_name="codex",
            capture_mode="autonomous",
        ),
        score_reasons=["near duplicate needs review"],
        created_at="2026-04-10T12:00:00Z",
        updated_at="2026-04-10T12:00:00Z",
    )
