from __future__ import annotations

import json
from pathlib import Path

from memwiz.config import build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Score
from memwiz.storage import write_workspace_canon


def test_context_uses_existing_digest_when_present(run_memwiz, tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
    digest_path = config.workspace_cache / "digest.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text("# Existing Digest\nUse the compiled digest.\n", encoding="utf-8")

    result = run_memwiz(
        "context",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
        "--scope",
        "workspace",
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["scope"] == "workspace"
    assert payload["text"] == "# Existing Digest\nUse the compiled digest.\n"


def test_context_falls_back_to_bounded_canon_rendering_when_digest_missing(
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
        "context",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
        "--scope",
        "workspace",
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["scope"] == "workspace"
    assert payload["included_record_ids"] == ["mem_20260410_11111111"]
    assert payload["omitted_count"] == 0
    assert "Workflow review guide" in payload["text"]


def test_context_never_leaks_other_workspace_records(run_memwiz, tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Task Space", env={})
    other_config = build_config(root=tmp_path, workspace="Other Space", env={})
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260410_11111111",
            workspace=config.workspace_slug,
            summary="Task-space workflow review guide",
        ),
    )
    write_workspace_canon(
        other_config,
        accepted_workspace_record(
            "mem_20260410_22222222",
            workspace=other_config.workspace_slug,
            summary="Other-space workflow review guide",
        ),
    )

    result = run_memwiz(
        "context",
        "--root",
        str(tmp_path),
        "--workspace",
        "Task Space",
        "--scope",
        "workspace",
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert "Task-space workflow review guide" in payload["text"]
    assert "Other-space workflow review guide" not in payload["text"]
    assert payload["included_record_ids"] == ["mem_20260410_11111111"]


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
