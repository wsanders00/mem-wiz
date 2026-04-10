from __future__ import annotations

import json
from pathlib import Path

from memwiz.cli import main
from memwiz.auditlog import read_audit_events
from memwiz.config import build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Origin, Score
from memwiz.remembering import remember
from memwiz.serde import read_record
from memwiz.storage import initialize_root, list_workspace_records, write_workspace_canon


def test_remember_auto_accepts_balanced_workflow_with_non_agent_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = build_config(root=tmp_path, workspace="Mem Wiz", env={})
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-10T12:00:00Z")

    result = remember(
        config,
        kind="workflow",
        summary="Run pytest -q before merge",
        details=None,
        tags=(),
        evidence_source="command",
        evidence_ref="pytest -q",
        actor_name="codex",
        policy_profile="balanced",
    )

    canon_records = list_workspace_records(config, "canon")

    assert result.outcome == "auto_accepted"
    assert result.accepted is True
    assert result.review_required is False
    assert list_workspace_records(config, "inbox") == []
    assert len(canon_records) == 1

    accepted = read_record(canon_records[0])
    assert accepted.origin is not None
    assert accepted.origin.actor_type == "agent"
    assert accepted.origin.actor_name == "codex"
    assert accepted.origin.capture_mode == "autonomous"
    assert accepted.decision is not None
    assert accepted.decision.accepted_mode == "policy"
    assert accepted.decision.accepted_by == "balanced"

    audit_events = read_audit_events(config)
    assert len(audit_events) == 1
    assert audit_events[0]["outcome"] == "auto_accepted"


def test_remember_skips_strong_duplicate_without_writing_second_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = build_config(root=tmp_path, workspace="Mem Wiz", env={})
    initialize_root(config)
    write_workspace_canon(
        config,
        make_workspace_accepted_record(
            workspace=config.workspace_slug,
            record_id="mem_20260410_abc123ef",
            summary="Run pytest -q before merge",
        ),
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-10T12:00:00Z")

    result = remember(
        config,
        kind="workflow",
        summary="Run pytest -q before merge",
        details=None,
        tags=(),
        evidence_source="command",
        evidence_ref="pytest -q",
        actor_name="codex",
        policy_profile="balanced",
    )

    assert result.outcome == "skipped_duplicate"
    assert result.accepted is False
    assert result.review_required is False
    assert list_workspace_records(config, "inbox") == []
    assert len(list_workspace_records(config, "canon")) == 1

    audit_events = read_audit_events(config)
    assert len(audit_events) == 1
    assert audit_events[0]["outcome"] == "skipped_duplicate"


def test_remember_marks_near_duplicate_for_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = build_config(root=tmp_path, workspace="Mem Wiz", env={})
    initialize_root(config)
    write_workspace_canon(
        config,
        make_workspace_accepted_record(
            workspace=config.workspace_slug,
            record_id="mem_20260410_abc123ef",
            summary="Run pytest before merge in this repository",
        ),
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-10T12:00:00Z")

    result = remember(
        config,
        kind="workflow",
        summary="Run pytest -q before merge in this repository",
        details=None,
        tags=(),
        evidence_source="command",
        evidence_ref="pytest -q",
        actor_name="codex",
        policy_profile="balanced",
    )

    inbox_records = list_workspace_records(config, "inbox")

    assert result.outcome == "review_required"
    assert result.accepted is False
    assert result.review_required is True
    assert "near_duplicate" in result.reason_codes
    assert len(inbox_records) == 1
    assert len(list_workspace_records(config, "canon")) == 1

    captured = read_record(inbox_records[0])
    assert captured.status == "captured"
    assert captured.score is not None

    audit_events = read_audit_events(config)
    assert len(audit_events) == 1
    assert audit_events[0]["outcome"] == "review_required"


def test_remember_command_json_output_returns_result_mapping(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-10T12:00:00Z")

    exit_code = main(
        [
            "remember",
            "--root",
            str(tmp_path),
            "--workspace",
            "Mem Wiz",
            "--kind",
            "workflow",
            "--summary",
            "Run pytest -q before merge",
            "--evidence-source",
            "command",
            "--evidence-ref",
            "pytest -q",
            "--actor-name",
            "codex",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["outcome"] == "auto_accepted"
    assert payload["accepted"] is True
    assert payload["review_required"] is False


def make_workspace_accepted_record(
    *,
    workspace: str,
    record_id: str,
    summary: str,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=2,
        id=record_id,
        scope="workspace",
        workspace=workspace,
        kind="workflow",
        summary=summary,
        details="Durable review workflow guidance.",
        evidence=[EvidenceItem(source="command", ref="pytest -q")],
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
            accepted_at="2026-04-10T11:00:00Z",
            accepted_mode="manual",
        ),
        origin=Origin(
            actor_type="user",
            capture_mode="manual",
        ),
        score_reasons=["durable enough to retain"],
        created_at="2026-04-10T11:00:00Z",
        updated_at="2026-04-10T11:00:00Z",
    )
