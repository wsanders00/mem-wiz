from __future__ import annotations

from pathlib import Path

import pytest

from memwiz.cli import main
from memwiz.config import build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score
from memwiz.serde import read_record
from memwiz.storage import (
    initialize_root,
    list_global_records,
    list_workspace_records,
    write_global_canon,
    write_workspace_canon,
)


def test_promotion_requires_an_accepted_workspace_record(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "mem-root"
    record_id = capture_and_score_workspace_candidate(
        root,
        monkeypatch,
        summary="Promote durable review guidance across repositories.",
        details="This guidance stays useful in future repos.",
    )

    exit_code = main(
        ["promote", "--root", str(root), "--workspace", "Task Space", "--id", record_id]
    )
    captured = capsys.readouterr()
    config = build_config(root=root, workspace="Task Space", env={})

    assert exit_code == 3
    assert "accepted workspace record not found" in captured.err.lower()
    assert list_global_records(config, "canon") == []


@pytest.mark.parametrize(
    ("summary", "details", "evidence_sources"),
    [
        (
            "This repo only uses bug-first review phrasing.",
            "This repository-specific convention is not portable.",
            ["conversation"],
        ),
        (
            "Promote today-only deploy guidance.",
            "Temporary today-only workflow note.",
            ["conversation"],
        ),
        (
            "Maybe promote this review preference later.",
            "This is just an unsupported guess.",
            ["agent"],
        ),
    ],
)
def test_promotion_enforces_score_durability_and_evidence_gates(
    tmp_path: Path,
    monkeypatch,
    capsys,
    summary: str,
    details: str,
    evidence_sources: list[str],
) -> None:
    root = tmp_path / "mem-root"
    config = build_config(root=root, workspace="Task Space", env={})
    initialize_root(config)
    record = make_workspace_accepted_record(
        workspace=config.workspace_slug,
        record_id="mem_20260408_abc123ef",
        summary=summary,
        details=details,
        evidence_sources=evidence_sources,
    )
    write_workspace_canon(config, record)
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T17:00:00Z")

    exit_code = main(
        ["promote", "--root", str(root), "--workspace", "Task Space", "--id", record.id]
    )
    captured = capsys.readouterr()

    assert exit_code == 4
    assert "promote rejected" in captured.err.lower()
    assert list_global_records(config, "canon") == []
    assert read_record(list_workspace_records(config, "canon")[0]).status == "accepted"


def test_promotion_blocks_when_strong_duplicate_exists_in_global_canon(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "mem-root"
    config = build_config(root=root, workspace="Task Space", env={})
    initialize_root(config)
    workspace_record = make_workspace_accepted_record(
        workspace=config.workspace_slug,
        record_id="mem_20260408_abc123ef",
        summary="Promote durable review guidance across repositories.",
        details="This guidance stays useful in future repos.",
    )
    write_workspace_canon(config, workspace_record)
    write_global_canon(
        config,
        make_global_accepted_record(
            record_id="mem_20260408_def456ab",
            summary="Promote durable review guidance across repositories.",
            source_memory_id="mem_20260408_fff99999",
        ),
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T17:00:00Z")

    exit_code = main(
        ["promote", "--root", str(root), "--workspace", "Task Space", "--id", workspace_record.id]
    )
    captured = capsys.readouterr()

    assert exit_code == 4
    assert "strong duplicates" in captured.err.lower()
    assert len(list_global_records(config, "canon")) == 1
    assert read_record(list_workspace_records(config, "canon")[0]).status == "accepted"


def test_promoted_global_records_include_provenance_and_both_score_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "mem-root"
    record_id = create_accepted_workspace_record(
        root,
        monkeypatch,
        summary="Promote durable review guidance across repositories.",
        details="This guidance stays useful in future repos.",
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T18:00:00Z")

    exit_code = main(
        ["promote", "--root", str(root), "--workspace", "Task Space", "--id", record_id]
    )
    config = build_config(root=root, workspace="Task Space", env={})
    global_records = list_global_records(config, "canon")
    workspace_records = list_workspace_records(config, "canon")

    assert exit_code == 0
    assert len(global_records) == 1
    promoted = read_record(global_records[0])
    assert promoted.scope == "global"
    assert promoted.workspace is None
    assert promoted.score is not None
    assert promoted.score.retain is not None
    assert promoted.score.promote is not None
    assert promoted.provenance is not None
    assert promoted.provenance.source_scope == "workspace"
    assert promoted.provenance.source_workspace == "task-space"
    assert promoted.provenance.source_memory_id == record_id
    assert promoted.decision is not None
    assert promoted.decision.accepted_at == "2026-04-08T18:00:00Z"
    assert promoted.updated_at == "2026-04-08T18:00:00Z"
    assert len(workspace_records) == 1
    assert read_record(workspace_records[0]).status == "accepted"


def create_accepted_workspace_record(
    root: Path,
    monkeypatch,
    *,
    summary: str,
    details: str,
) -> str:
    record_id = capture_and_score_workspace_candidate(
        root,
        monkeypatch,
        summary=summary,
        details=details,
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T17:00:00Z")
    exit_code = main(
        ["accept", "--root", str(root), "--workspace", "Task Space", "--id", record_id]
    )
    assert exit_code == 0
    return record_id


def capture_and_score_workspace_candidate(
    root: Path,
    monkeypatch,
    *,
    summary: str,
    details: str,
) -> str:
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T15:30:00Z")
    assert (
        main(
            [
                "capture",
                "--root",
                str(root),
                "--workspace",
                "Task Space",
                "--kind",
                "workflow",
                "--summary",
                summary,
                "--details",
                details,
                "--evidence-source",
                "conversation",
                "--evidence-ref",
                "turn:user:2026-04-08",
            ]
        )
        == 0
    )
    config = build_config(root=root, workspace="Task Space", env={})
    record_id = read_record(list_workspace_records(config, "inbox")[0]).id
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T16:00:00Z")
    assert (
        main(["score", "--root", str(root), "--workspace", "Task Space", "--id", record_id])
        == 0
    )
    return record_id


def make_workspace_accepted_record(
    *,
    workspace: str,
    record_id: str,
    summary: str,
    details: str,
    evidence_sources: list[str] | None = None,
) -> MemoryRecord:
    sources = evidence_sources or ["conversation"]
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="workspace",
        workspace=workspace,
        kind="workflow",
        summary=summary,
        details=details,
        evidence=[EvidenceItem(source=source, ref=f"{source}:evidence") for source in sources],
        score=Score(
            reuse=0.75,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=1.0,
            scope_fit=1.0,
            retain=0.90,
        ),
        status="accepted",
        decision=Decision(accepted_at="2026-04-08T16:30:00Z"),
        score_reasons=["durable enough to retain"],
        created_at="2026-04-08T16:30:00Z",
        updated_at="2026-04-08T16:30:00Z",
    )


def make_global_accepted_record(
    *,
    record_id: str,
    summary: str,
    source_memory_id: str,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="global",
        workspace=None,
        kind="workflow",
        summary=summary,
        details="Existing promoted record in global canon.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=1.0,
            scope_fit=1.0,
            retain=1.0,
            promote=0.90,
        ),
        status="accepted",
        decision=Decision(accepted_at="2026-04-08T17:00:00Z"),
        score_reasons=["already promoted"],
        provenance=Provenance(
            source_scope="workspace",
            source_workspace="task-space",
            source_memory_id=source_memory_id,
            promoted_at="2026-04-08T17:00:00Z",
            promotion_reason="Already promoted.",
        ),
        created_at="2026-04-08T17:00:00Z",
        updated_at="2026-04-08T17:00:00Z",
    )
