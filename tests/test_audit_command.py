from __future__ import annotations

import json
from pathlib import Path

from memwiz.auditlog import append_audit_event
from memwiz.config import build_config


def test_audit_json_filters_by_outcome(run_memwiz, tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T12:00:00Z",
            "workspace": config.workspace_slug,
            "memory_id": "mem_20260410_deadbeef",
            "actor": {"type": "agent", "name": "codex"},
            "action": "remember",
            "outcome": "auto_accepted",
            "reason_codes": [],
            "score_snapshot": {"retain": 0.95},
            "summary_preview": "Run pytest -q before merge",
            "evidence_summary": ["command:pytest -q"],
            "policy_profile": "balanced",
            "needs_user": False,
        },
    )
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T13:00:00Z",
            "workspace": config.workspace_slug,
            "memory_id": "mem_20260410_feedface",
            "actor": {"type": "agent", "name": "codex"},
            "action": "remember",
            "outcome": "review_required",
            "reason_codes": ["near_duplicate"],
            "score_snapshot": {"retain": 0.75},
            "summary_preview": "Run pytest before merge in this repository",
            "evidence_summary": ["command:pytest -q"],
            "policy_profile": "balanced",
            "needs_user": True,
        },
    )

    result = run_memwiz(
        "audit",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
        "--outcome",
        "review_required",
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert len(payload["events"]) == 1
    assert payload["events"][0]["outcome"] == "review_required"
    assert payload["events"][0]["memory_id"] == "mem_20260410_feedface"


def test_audit_json_filters_by_reason_code_and_limit(run_memwiz, tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
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
            "score_snapshot": {"retain": 0.70},
            "summary_preview": "Older near-duplicate guidance",
            "evidence_summary": ["command:pytest -q"],
            "policy_profile": "balanced",
            "needs_user": True,
        },
    )
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T13:00:00Z",
            "workspace": config.workspace_slug,
            "memory_id": "mem_20260410_cafefeed",
            "actor": {"type": "agent", "name": "codex"},
            "action": "remember",
            "outcome": "auto_accepted",
            "reason_codes": [],
            "score_snapshot": {"retain": 0.95},
            "summary_preview": "Accepted guidance",
            "evidence_summary": ["command:pytest -q"],
            "policy_profile": "balanced",
            "needs_user": False,
        },
    )
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T14:00:00Z",
            "workspace": config.workspace_slug,
            "memory_id": "mem_20260410_feedface",
            "actor": {"type": "agent", "name": "codex"},
            "action": "remember",
            "outcome": "review_required",
            "reason_codes": ["near_duplicate", "requires_non_agent_evidence"],
            "score_snapshot": {"retain": 0.72},
            "summary_preview": "Newest near-duplicate guidance",
            "evidence_summary": ["agent:self"],
            "policy_profile": "balanced",
            "needs_user": True,
        },
    )

    result = run_memwiz(
        "audit",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
        "--reason-code",
        "near_duplicate",
        "--limit",
        "1",
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert len(payload["events"]) == 1
    assert payload["events"][0]["memory_id"] == "mem_20260410_feedface"
