from __future__ import annotations

from pathlib import Path

from memwiz.auditlog import append_audit_event, read_audit_events
from memwiz.config import build_config


def test_append_audit_event_writes_jsonl_record(tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Mem Wiz", env={})

    result = append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T12:00:00Z",
            "workspace": "mem-wiz",
            "memory_id": "mem_20260410_deadbeef",
            "outcome": "captured",
        },
    )

    assert result.path == config.audit_root / "2026-04-10.jsonl"
    assert result.path.exists()
    assert "captured" in result.path.read_text(encoding="utf-8")


def test_append_audit_event_fsyncs_parent_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = build_config(root=tmp_path, workspace="Mem Wiz", env={})
    recorded_paths: list[Path] = []

    def recording_fsync_directory(path: Path) -> None:
        recorded_paths.append(path)

    monkeypatch.setattr("memwiz.auditlog.fsync_directory", recording_fsync_directory)

    append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T12:00:00Z",
            "workspace": "mem-wiz",
            "memory_id": "mem_20260410_deadbeef",
            "outcome": "captured",
        },
    )

    assert recorded_paths == [config.audit_root]


def test_read_audit_events_filters_by_workspace_and_outcome(tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Mem Wiz", env={})
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-10T12:00:00Z",
            "workspace": "mem-wiz",
            "memory_id": "mem_20260410_deadbeef",
            "outcome": "captured",
        },
    )
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-11T12:00:00Z",
            "workspace": "other-space",
            "memory_id": "mem_20260411_feedface",
            "outcome": "review_required",
        },
    )
    append_audit_event(
        config,
        {
            "timestamp": "2026-04-11T13:00:00Z",
            "workspace": "mem-wiz",
            "memory_id": "mem_20260411_cafebabe",
            "outcome": "review_required",
        },
    )

    events = read_audit_events(
        config,
        workspace="mem-wiz",
        outcome="review_required",
    )

    assert [event["memory_id"] for event in events] == ["mem_20260411_cafebabe"]
