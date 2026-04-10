from __future__ import annotations

import json
from pathlib import Path

from memwiz.config import build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Score
from memwiz.storage import write_workspace_canon


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
