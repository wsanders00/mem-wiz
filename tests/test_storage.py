from __future__ import annotations

from pathlib import Path

from memwiz.clock import CommandClock
from memwiz.config import build_config
from memwiz.models import (
    Decision,
    EvidenceItem,
    MemoryRecord,
    Provenance,
    Score,
)
from memwiz.serde import read_record
from memwiz import storage


def test_initialize_root_creates_global_tree_without_global_inbox(tmp_path: Path) -> None:
    config = build_config(root=tmp_path / "mem-root", workspace="mem-wiz", env={})

    storage.initialize_root(config)

    assert config.root.exists()
    assert (config.root / "workspaces").is_dir()
    assert config.global_root.is_dir()
    assert config.global_canon.is_dir()
    assert config.global_archive.is_dir()
    assert config.global_cache.is_dir()
    assert not (config.global_root / "inbox").exists()
    assert not config.workspace_root.exists()


def test_write_workspace_candidate_places_record_in_inbox(tmp_path: Path) -> None:
    config = build_config(root=tmp_path / "mem-root", workspace="mem-wiz", env={})
    storage.initialize_root(config)
    record = make_workspace_captured_record(workspace=config.workspace_slug)

    path = storage.write_workspace_candidate(config, record)

    assert path == config.workspace_inbox / f"{record.id}.yaml"
    assert read_record(path) == record
    assert storage.list_workspace_records(config, "inbox") == [path]


def test_write_workspace_accepted_places_record_in_canon(tmp_path: Path) -> None:
    config = build_config(root=tmp_path / "mem-root", workspace="mem-wiz", env={})
    storage.initialize_root(config)
    record = make_workspace_accepted_record(workspace=config.workspace_slug)

    path = storage.write_workspace_canon(config, record)

    assert path == config.workspace_canon / f"{record.id}.yaml"
    assert read_record(path) == record
    assert storage.list_workspace_records(config, "canon") == [path]


def test_write_promoted_global_record_places_record_in_global_canon(tmp_path: Path) -> None:
    config = build_config(root=tmp_path / "mem-root", workspace="mem-wiz", env={})
    storage.initialize_root(config)
    record = make_global_accepted_record()

    path = storage.write_global_canon(config, record)

    assert path == config.global_canon / f"{record.id}.yaml"
    assert read_record(path) == record
    assert storage.list_global_records(config, "canon") == [path]


def test_archive_workspace_record_moves_record_by_memory_id_and_updates_metadata(
    tmp_path: Path,
    make_fixed_clock,
) -> None:
    config = build_config(root=tmp_path / "mem-root", workspace="mem-wiz", env={})
    storage.initialize_root(config)
    record = make_workspace_accepted_record(workspace=config.workspace_slug)
    source_path = storage.write_workspace_canon(config, record)
    command_clock = CommandClock(make_fixed_clock("2026-04-08T16:00:00Z"))

    archived_path = storage.archive_workspace_record(
        config,
        record.id,
        archive_reason="superseded by newer workflow",
        command_clock=command_clock,
    )

    archived_record = read_record(archived_path)

    assert archived_path == config.workspace_archive / f"{record.id}.yaml"
    assert not source_path.exists()
    assert archived_record.status == "archived"
    assert archived_record.updated_at == "2026-04-08T16:00:00Z"
    assert archived_record.decision is not None
    assert archived_record.decision.archived_at == "2026-04-08T16:00:00Z"
    assert archived_record.decision.archive_reason == "superseded by newer workflow"


def test_archive_global_record_moves_record_by_memory_id_and_updates_metadata(
    tmp_path: Path,
    make_fixed_clock,
) -> None:
    config = build_config(root=tmp_path / "mem-root", workspace="mem-wiz", env={})
    storage.initialize_root(config)
    record = make_global_accepted_record()
    source_path = storage.write_global_canon(config, record)
    command_clock = CommandClock(make_fixed_clock("2026-04-08T16:00:00Z"))

    archived_path = storage.archive_global_record(
        config,
        record.id,
        archive_reason="strong-duplicate-of:mem_20260408_aaaa1111",
        command_clock=command_clock,
    )

    archived_record = read_record(archived_path)

    assert archived_path == config.global_archive / f"{record.id}.yaml"
    assert not source_path.exists()
    assert archived_record.status == "archived"
    assert archived_record.updated_at == "2026-04-08T16:00:00Z"
    assert archived_record.decision is not None
    assert archived_record.decision.archived_at == "2026-04-08T16:00:00Z"
    assert archived_record.decision.archive_reason == "strong-duplicate-of:mem_20260408_aaaa1111"


def make_workspace_captured_record(*, workspace: str) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id="mem_20260408_abc123ef",
        scope="workspace",
        workspace=workspace,
        kind="workflow",
        summary="Store captured workspace notes in inbox first.",
        details=None,
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        confidence="medium",
        score=None,
        status="captured",
        tags=["capture-flow"],
        decision=None,
        score_reasons=None,
        supersedes=None,
        provenance=None,
        created_at="2026-04-08T15:30:00Z",
        updated_at="2026-04-08T15:30:00Z",
    )


def make_workspace_accepted_record(*, workspace: str) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id="mem_20260408_abc123ef",
        scope="workspace",
        workspace=workspace,
        kind="workflow",
        summary="Store accepted workspace notes in canon.",
        details="Accepted workspace memories should move out of inbox.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=0.75,
            scope_fit=1.0,
            retain=0.96,
        ),
        status="accepted",
        tags=["canon-flow"],
        decision=Decision(accepted_at="2026-04-08T15:30:00Z"),
        score_reasons=["durable workflow", "reusable convention"],
        supersedes=None,
        provenance=None,
        created_at="2026-04-08T15:30:00Z",
        updated_at="2026-04-08T15:30:00Z",
    )


def make_global_accepted_record() -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id="mem_20260408_def456ab",
        scope="global",
        workspace=None,
        kind="workflow",
        summary="Promoted global memories live in global canon.",
        details="Global canon stores explicit promotions from workspace memory.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=0.75,
            scope_fit=1.0,
            retain=0.94,
            promote=0.82,
        ),
        status="accepted",
        tags=["global-canon"],
        decision=Decision(accepted_at="2026-04-08T15:30:00Z"),
        score_reasons=["durable across workspaces", "high evidence"],
        supersedes=None,
        provenance=Provenance(
            source_scope="workspace",
            source_workspace="mem-wiz",
            source_memory_id="mem_20260408_abc123ef",
            promoted_at="2026-04-08T15:30:00Z",
            promotion_reason="Useful across future workspaces.",
        ),
        created_at="2026-04-08T15:30:00Z",
        updated_at="2026-04-08T15:30:00Z",
    )
