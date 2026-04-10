from __future__ import annotations

import json
from pathlib import Path

from memwiz.config import build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score
from memwiz.storage import write_global_canon, write_workspace_canon


def test_search_json_output_returns_hits_list(run_memwiz, tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260410_11111111",
            workspace=config.workspace_slug,
            summary="Workflow review guide",
        ),
    )
    write_global_canon(
        config,
        accepted_global_record(
            "mem_20260410_22222222",
            summary="Workflow review defaults",
        ),
    )

    result = run_memwiz(
        "search",
        "workflow review",
        "--format",
        "json",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["query"] == "workflow review"
    assert payload["scope"] == "all"
    assert payload["limit"] == 10
    assert len(payload["hits"]) == 2
    assert payload["hits"][0]["id"] == "mem_20260410_11111111"
    assert payload["hits"][0]["workspace"] == "task-space"


def test_get_json_output_returns_record_mapping(run_memwiz, tmp_path: Path) -> None:
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
        "get",
        "--id",
        "mem_20260410_11111111",
        "--format",
        "json",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["id"] == "mem_20260410_11111111"
    assert payload["workspace"] == "task-space"
    assert payload["status"] == "accepted"


def test_doctor_json_output_returns_findings_list(run_memwiz, tmp_path: Path) -> None:
    result = run_memwiz(
        "doctor",
        "--format",
        "json",
        "--root",
        str(tmp_path / "missing-root"),
        "--workspace",
        "Task Space",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["code"] == "root-missing"


def test_compile_json_output_returns_plan_list(run_memwiz, tmp_path: Path) -> None:
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
        "compile",
        "--format",
        "json",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert len(payload) == 1
    assert payload[0]["scope"] == "workspace"
    assert payload[0]["workspace_label"] == "task-space"
    assert payload[0]["included_count"] == 1


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


def accepted_global_record(
    record_id: str,
    *,
    summary: str,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=2,
        id=record_id,
        scope="global",
        workspace=None,
        kind="workflow",
        summary=summary,
        details="Durable workflow guidance for future sessions.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-10")],
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=1.0,
            scope_fit=1.0,
            retain=1.0,
            promote=0.9,
        ),
        status="accepted",
        decision=Decision(
            accepted_at="2026-04-10T09:00:00Z",
            accepted_mode="manual",
        ),
        score_reasons=["durable enough to retain"],
        provenance=Provenance(
            source_scope="workspace",
            source_workspace="task-space",
            source_memory_id="mem_20260410_11111111",
            promoted_at="2026-04-10T10:00:00Z",
            promotion_reason="Durable workflow guidance.",
        ),
        created_at="2026-04-10T10:00:00Z",
        updated_at="2026-04-10T10:00:00Z",
    )
