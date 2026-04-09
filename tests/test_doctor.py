from __future__ import annotations

from pathlib import Path

import pytest

import memwiz.fsops as fsops
from memwiz.cli import main
from memwiz.config import MemwizConfig, build_config
from memwiz.doctoring import run_doctor
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score
from memwiz.serde import dump_record
from memwiz.storage import initialize_root


def test_run_doctor_reports_missing_root(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    findings = run_doctor(config)

    assert [(finding.level, finding.code, finding.subject) for finding in findings] == [
        ("error", "root-missing", str(config.root))
    ]


def test_run_doctor_accepts_initialized_root_without_findings(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    initialize_root(config)

    findings = run_doctor(config)

    assert findings == []


def test_run_doctor_reports_missing_required_global_directories(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.root.mkdir(parents=True)

    findings = run_doctor(config)

    assert [finding.code for finding in findings] == ["path-missing"] * 5
    assert [finding.subject for finding in findings] == sorted(
        [finding.subject for finding in findings]
    )
    assert {finding.subject for finding in findings} == {
        str(config.root / "workspaces"),
        str(config.global_root),
        str(config.global_canon),
        str(config.global_archive),
        str(config.global_cache),
    }


def test_run_doctor_reports_partial_workspace_tree_when_workspace_root_exists(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    config.workspace_root.mkdir(parents=True)
    config.workspace_inbox.mkdir()

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("path-missing", str(config.workspace_archive)),
        ("path-missing", str(config.workspace_cache)),
        ("path-missing", str(config.workspace_canon)),
    ]


def test_run_doctor_reports_non_writable_required_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)

    def fake_access(path: object, mode: int) -> bool:
        if Path(path) == config.global_cache:
            return False

        return True

    monkeypatch.setattr("memwiz.doctoring.os.access", fake_access)

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("path-not-writable", str(config.global_cache))
    ]


def test_run_doctor_reports_non_writable_root_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)

    def fake_access(path: object, mode: int) -> bool:
        if Path(path) == config.root:
            return False

        return True

    monkeypatch.setattr("memwiz.doctoring.os.access", fake_access)

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("path-not-writable", str(config.root))
    ]


def test_run_doctor_reports_stale_root_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    fsops.root_lock_path(config.root).write_text("999999\n", encoding="utf-8")

    def raise_process_lookup_error(pid: int, signal: int) -> None:
        raise ProcessLookupError(pid)

    monkeypatch.setattr(fsops.os, "kill", raise_process_lookup_error)

    findings = run_doctor(config)

    assert [(finding.level, finding.code, finding.subject) for finding in findings] == [
        ("warn", "lock-stale", str(fsops.root_lock_path(config.root)))
    ]


def test_run_doctor_reports_invalid_root_lock_contents(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    fsops.root_lock_path(config.root).write_text("not-a-pid\n", encoding="utf-8")

    findings = run_doctor(config)

    assert [(finding.level, finding.code, finding.subject) for finding in findings] == [
        ("warn", "lock-invalid", str(fsops.root_lock_path(config.root)))
    ]


def test_run_doctor_reports_unreadable_root_lock_as_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    lock_path = fsops.root_lock_path(config.root)
    lock_path.write_text("12345\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == lock_path:
            raise PermissionError("permission denied")

        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(fsops.Path, "read_text", fake_read_text)

    findings = run_doctor(config)

    assert [(finding.level, finding.code, finding.subject) for finding in findings] == [
        ("warn", "lock-invalid", str(lock_path))
    ]


def test_run_doctor_reports_decode_failure_for_corrupt_canon_yaml(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    (config.global_canon / "mem_20260408_deadbeef.yaml").write_text(
        "{\n",
        encoding="utf-8",
    )

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("record-decode", str(config.global_canon / "mem_20260408_deadbeef.yaml"))
    ]


def test_run_doctor_reports_decode_failure_for_unreadable_record_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    path = config.global_canon / "mem_20260408_deadbeef.yaml"
    path.write_text("id: mem_20260408_deadbeef\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == path:
            raise PermissionError("permission denied")

        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.read_text", fake_read_text)

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("record-decode", str(path))
    ]


def test_run_doctor_reports_schema_invalid_record_with_missing_required_field(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    path = config.global_canon / "mem_20260408_deadbeef.yaml"
    path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: mem_20260408_deadbeef",
                "scope: global",
                "kind: workflow",
                "evidence:",
                "  - source: conversation",
                "    ref: turn:user:task-1",
                "status: accepted",
                "created_at: 2026-04-08T15:30:00Z",
                "updated_at: 2026-04-08T15:30:00Z",
                "score:",
                "  reuse: 1.0",
                "  specificity: 1.0",
                "  durability: 1.0",
                "  evidence: 1.0",
                "  novelty: 0.8",
                "  scope_fit: 1.0",
                "  retain: 0.95",
                "  promote: 0.9",
                "decision:",
                "  accepted_at: 2026-04-08T15:30:00Z",
                "score_reasons:",
                "  - structural health check fixture",
                "provenance:",
                "  source_scope: workspace",
                "  source_workspace: alpha",
                "  source_memory_id: mem_20260408_c0ffee00",
                "  promoted_at: 2026-04-08T15:30:00Z",
                "  promotion_reason: fixture provenance",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("record-invalid", str(path))
    ]


def test_run_doctor_reports_record_path_mismatch_for_misnamed_canon_record(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    record = make_record(
        record_id="mem_20260408_deadbeef",
        scope="global",
        workspace=None,
        status="accepted",
    )
    path = config.global_canon / "mem_20260408_feedface.yaml"
    path.write_text(dump_record(record), encoding="utf-8")

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("record-path-mismatch", str(path))
    ]


def test_run_doctor_reports_invalid_archive_status_for_workspace_archive_record(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    config.workspace_archive.mkdir(parents=True)
    config.workspace_canon.mkdir(parents=True)
    config.workspace_inbox.mkdir(parents=True)
    config.workspace_cache.mkdir(parents=True)
    record = make_record(
        record_id="mem_20260408_deadbeef",
        scope="workspace",
        workspace=config.workspace_slug,
        status="accepted",
    )
    (config.workspace_archive / f"{record.id}.yaml").write_text(
        dump_record(record),
        encoding="utf-8",
    )

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("record-invalid", str(config.workspace_archive / f"{record.id}.yaml"))
    ]


def test_run_doctor_reports_scope_path_mismatch_for_global_record_in_workspace_tree(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    config.workspace_archive.mkdir(parents=True)
    config.workspace_canon.mkdir(parents=True)
    config.workspace_inbox.mkdir(parents=True)
    config.workspace_cache.mkdir(parents=True)
    record = make_record(
        record_id="mem_20260408_deadbeef",
        scope="global",
        workspace=None,
        status="accepted",
    )
    (config.workspace_canon / f"{record.id}.yaml").write_text(
        dump_record(record),
        encoding="utf-8",
    )

    findings = run_doctor(config)

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("record-invalid", str(config.workspace_canon / f"{record.id}.yaml")),
        ("record-invalid", str(config.workspace_canon / f"{record.id}.yaml")),
    ]


def test_run_doctor_does_not_inspect_inbox_records(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    config.workspace_archive.mkdir(parents=True)
    config.workspace_canon.mkdir(parents=True)
    config.workspace_inbox.mkdir(parents=True)
    config.workspace_cache.mkdir(parents=True)
    (config.workspace_inbox / "mem_20260408_deadbeef.yaml").write_text(
        "{\n",
        encoding="utf-8",
    )

    findings = run_doctor(config)

    assert findings == []


def test_run_doctor_orders_findings_by_category_and_preserves_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    lock_path = fsops.root_lock_path(config.root)
    lock_path.write_text("999999\n", encoding="utf-8")
    config.global_archive.rmdir()
    config.workspace_root.mkdir(parents=True)
    config.workspace_inbox.mkdir()
    record_path = config.global_canon / "mem_20260408_deadbeef.yaml"
    record_path.write_text("id: mem_20260408_deadbeef\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_access(path: object, mode: int) -> bool:
        return Path(path) != config.root

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == record_path:
            raise PermissionError("permission denied")

        return original_read_text(self, *args, **kwargs)

    def raise_process_lookup_error(pid: int, signal: int) -> None:
        raise ProcessLookupError(pid)

    monkeypatch.setattr("memwiz.doctoring.os.access", fake_access)
    monkeypatch.setattr("pathlib.Path.read_text", fake_read_text)
    monkeypatch.setattr(fsops.os, "kill", raise_process_lookup_error)

    findings = run_doctor(config)

    assert [
        (finding.level, finding.code, finding.subject, finding.message)
        for finding in findings
    ] == [
        (
            "error",
            "path-not-writable",
            str(config.root),
            "required path is not writable",
        ),
        (
            "warn",
            "lock-stale",
            str(lock_path),
            "stale lock file can be reclaimed",
        ),
        (
            "error",
            "path-missing",
            str(config.global_archive),
            "required directory is missing",
        ),
        (
            "error",
            "path-missing",
            str(config.workspace_archive),
            "required directory is missing",
        ),
        (
            "error",
            "path-missing",
            str(config.workspace_cache),
            "required directory is missing",
        ),
        (
            "error",
            "path-missing",
            str(config.workspace_canon),
            "required directory is missing",
        ),
        (
            "error",
            "record-decode",
            str(record_path),
            "failed to decode record: permission denied",
        ),
    ]


def test_doctor_command_returns_zero_with_exact_no_findings_message(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)

    exit_code = main(
        [
            "doctor",
            "--root",
            str(config.root),
            "--workspace",
            config.workspace_slug,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "No doctor findings.\n"
    assert captured.err == ""


def test_doctor_command_prints_findings_as_tab_separated_rows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)

    exit_code = main(
        [
            "doctor",
            "--root",
            str(config.root),
            "--workspace",
            config.workspace_slug,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == (
        f"error\troot-missing\t{config.root}\tmemory root does not exist\n"
    )
    assert captured.err == ""


def test_doctor_command_prints_multiple_findings_in_stable_order(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    config.root.mkdir(parents=True)

    exit_code = main(
        [
            "doctor",
            "--root",
            str(config.root),
            "--workspace",
            config.workspace_slug,
        ]
    )

    captured = capsys.readouterr()

    expected_subjects = sorted(
        [
            str(config.root / "workspaces"),
            str(config.global_root),
            str(config.global_canon),
            str(config.global_archive),
            str(config.global_cache),
        ]
    )

    assert exit_code == 1
    assert captured.out.splitlines() == [
        f"error\tpath-missing\t{subject}\trequired directory is missing"
        for subject in expected_subjects
    ]
    assert captured.err == ""


def make_config(tmp_path: Path) -> MemwizConfig:
    return build_config(root=tmp_path / "mem-root", workspace="alpha", env={})


def make_record(
    *,
    record_id: str,
    scope: str,
    workspace: str | None,
    status: str,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope=scope,
        workspace=workspace,
        kind="workflow",
        summary="Doctor validates structural memory health.",
        details=None,
        evidence=[EvidenceItem(source="conversation", ref="turn:user:task-1")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=0.8,
            scope_fit=1.0,
            retain=0.95,
            promote=0.9 if scope == "global" else None,
        ),
        status=status,
        tags=["doctor"],
        decision=Decision(
            accepted_at="2026-04-08T15:30:00Z",
            archived_at="2026-04-08T16:30:00Z" if status == "archived" else None,
            archive_reason="retired-by-doctor-test" if status == "archived" else None,
        ),
        score_reasons=["structural health check fixture"],
        supersedes=None,
        provenance=(
            Provenance(
                source_scope="workspace",
                source_workspace="alpha",
                source_memory_id="mem_20260408_c0ffee00",
                promoted_at="2026-04-08T15:30:00Z",
                promotion_reason="fixture provenance",
            )
            if scope == "global"
            else None
        ),
        created_at="2026-04-08T15:30:00Z",
        updated_at="2026-04-08T15:30:00Z",
    )
