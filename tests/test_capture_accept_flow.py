from __future__ import annotations

from pathlib import Path

import pytest

from memwiz.cli import main
from memwiz.config import build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Score
from memwiz.serde import read_record
from memwiz.storage import initialize_root, list_workspace_records, write_workspace_canon


def test_capture_writes_only_to_workspace_inbox(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "mem-root"
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T15:30:00Z")

    exit_code = main(
        [
            "capture",
            "--root",
            str(root),
            "--workspace",
            "Task Space",
            "--kind",
            "workflow",
            "--summary",
            "Capture durable workflow notes in workspace inbox.",
            "--details",
            "Workspace candidates should land in inbox before scoring.",
            "--tag",
            "capture-flow",
            "--evidence-source",
            "conversation",
            "--evidence-ref",
            "turn:user:2026-04-08",
        ]
    )

    config = build_config(root=root, workspace="Task Space", env={})
    inbox_records = list_workspace_records(config, "inbox")
    captured_record = read_record(inbox_records[0])

    assert exit_code == 0
    assert len(inbox_records) == 1
    assert list_workspace_records(config, "canon") == []
    assert captured_record.status == "captured"
    assert captured_record.schema_version == 2
    assert captured_record.origin is not None
    assert captured_record.origin.capture_mode == "manual"


def test_capture_rejects_secret_like_input_before_write(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "mem-root"
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T15:30:00Z")

    exit_code = main(
        [
            "capture",
            "--root",
            str(root),
            "--workspace",
            "Task Space",
            "--kind",
            "workflow",
            "--summary",
            "Store the secret token for later use.",
            "--evidence-source",
            "conversation",
            "--evidence-ref",
            "turn:user:2026-04-08",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 4
    assert "secret-like content" in captured.err
    assert not root.exists()


@pytest.mark.parametrize(
    "summary",
    [
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghi",
        "Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghi",
        "Bearer abcdefghijklmnop",
        "Store access_token=abcdefghi for later.",
        "Store token is abcdef+/= for later.",
        'Store token="abcdefghi" for later.',
        'Store access_token: "abcdefghi" for later.',
        "Store secret key = abcdefghijklmnop for later.",
        "db_password=supersecret1",
        "github_token=ghp_abcdefghijklmnop",
        "slack_api_key=xoxb-abcdefghijklmnop",
        "client_secret=abcdefghijklmnop",
    ],
)
def test_capture_rejects_common_secret_shapes(
    tmp_path: Path,
    monkeypatch,
    capsys,
    summary: str,
) -> None:
    root = tmp_path / "mem-root"
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T15:30:00Z")

    exit_code = main(
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
            "--evidence-source",
            "conversation",
            "--evidence-ref",
            "turn:user:2026-04-08",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 4
    assert "secret-like content" in captured.err
    assert not root.exists()


@pytest.mark.parametrize(
    ("summary", "details"),
    [
        (
            "Track token budget guidance for task-space prompt reviews.",
            "This workflow keeps prompts concise across future sessions.",
        ),
        (
            "Use bearer token auth on the internal API.",
            "This workflow note describes the expected auth scheme.",
        ),
        (
            "Use bearer authentication on the internal API.",
            "This workflow note describes the expected auth scheme.",
        ),
        (
            "Use bearer oauth2/jwt on the internal API.",
            "This workflow note describes the expected auth scheme.",
        ),
        (
            "Refresh token rotation is handled by the auth service.",
            "This is durable implementation guidance rather than a stored credential.",
        ),
        (
            "Access token is required for this flow.",
            "This note describes a protocol requirement rather than a credential value.",
        ),
        (
            "Access token is short-lived in this flow.",
            "This note describes token lifetime rather than a credential value.",
        ),
        (
            "Document password rotation policy for services.",
            "This note describes the operational policy rather than a password value.",
        ),
        (
            "Secret key rotation is handled by KMS.",
            "This note describes the operational policy rather than a stored credential value.",
        ),
        (
            "API key rotation is handled by the platform team.",
            "This note describes ownership rather than a stored credential value.",
        ),
        (
            "API key is required for requests to this service.",
            "This note describes a protocol requirement rather than a stored credential value.",
        ),
        (
            "API key is service-account scoped for this integration.",
            "This note describes credential scope rather than a stored credential value.",
        ),
    ],
)
def test_capture_allows_benign_secret_adjacent_language(
    tmp_path: Path,
    monkeypatch,
    summary: str,
    details: str,
) -> None:
    root = tmp_path / "mem-root"
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T15:30:00Z")

    exit_code = main(
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

    config = build_config(root=root, workspace="Task Space", env={})
    inbox_records = list_workspace_records(config, "inbox")

    assert exit_code == 0
    assert len(inbox_records) == 1
    assert read_record(inbox_records[0]).status == "captured"


def test_score_persists_factor_values_reasons_and_updated_timestamp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "mem-root"
    record_id = capture_candidate(
        root,
        monkeypatch,
        summary="Capture durable workflow notes in workspace inbox.",
        details="Workspace candidates should land in inbox before scoring.",
        timestamp="2026-04-08T15:30:00Z",
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T16:00:00Z")

    exit_code = main(
        [
            "score",
            "--root",
            str(root),
            "--workspace",
            "Task Space",
            "--id",
            record_id,
        ]
    )

    scored_record = workspace_inbox_record(root)

    assert exit_code == 0
    assert scored_record.score is not None
    assert scored_record.score.reuse == 0.75
    assert scored_record.score.specificity == 1.0
    assert scored_record.score.durability == 1.0
    assert scored_record.score.evidence == 1.0
    assert scored_record.score.novelty == 1.0
    assert scored_record.score.scope_fit == 1.0
    assert scored_record.score.retain is not None
    assert scored_record.score.retain == 0.94
    assert scored_record.score_reasons
    assert scored_record.updated_at == "2026-04-08T16:00:00Z"
    assert scored_record.created_at == "2026-04-08T15:30:00Z"


def test_accept_moves_retained_candidates_into_workspace_canon(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "mem-root"
    record_id = capture_candidate(
        root,
        monkeypatch,
        summary="Capture durable workflow notes in workspace inbox.",
        details="Workspace candidates should land in inbox before scoring.",
        timestamp="2026-04-08T15:30:00Z",
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T16:00:00Z")
    assert main(["score", "--root", str(root), "--workspace", "Task Space", "--id", record_id]) == 0
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T17:00:00Z")

    exit_code = main(
        ["accept", "--root", str(root), "--workspace", "Task Space", "--id", record_id]
    )
    config = build_config(root=root, workspace="Task Space", env={})
    canon_records = list_workspace_records(config, "canon")

    assert exit_code == 0
    assert list_workspace_records(config, "inbox") == []
    assert len(canon_records) == 1
    accepted = read_record(canon_records[0])
    assert accepted.status == "accepted"
    assert accepted.schema_version == 2
    assert accepted.origin is not None
    assert accepted.origin.capture_mode == "manual"
    assert accepted.decision is not None
    assert accepted.decision.accepted_at == "2026-04-08T17:00:00Z"
    assert accepted.decision.accepted_mode == "manual"
    assert accepted.updated_at == "2026-04-08T17:00:00Z"


def test_accept_recomputes_and_blocks_when_duplicate_checks_fail(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "mem-root"
    summary = "Capture durable workflow notes in workspace inbox."
    record_id = capture_candidate(
        root,
        monkeypatch,
        summary=summary,
        details="Workspace candidates should land in inbox before scoring.",
        timestamp="2026-04-08T15:30:00Z",
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T16:00:00Z")
    assert main(["score", "--root", str(root), "--workspace", "Task Space", "--id", record_id]) == 0

    config = build_config(root=root, workspace="Task Space", env={})
    initialize_root(config)
    write_workspace_canon(
        config,
        MemoryRecord(
            schema_version=1,
            id="mem_20260408_def456ab",
            scope="workspace",
            workspace=config.workspace_slug,
            kind="workflow",
            summary=summary,
            details="Accepted duplicate already lives in canon.",
            evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
            score=Score(
                reuse=0.75,
                specificity=1.0,
                durability=1.0,
                evidence=1.0,
                novelty=1.0,
                scope_fit=1.0,
                retain=0.94,
            ),
            status="accepted",
            decision=Decision(accepted_at="2026-04-08T16:30:00Z"),
            score_reasons=["already accepted"],
            created_at="2026-04-08T16:30:00Z",
            updated_at="2026-04-08T16:30:00Z",
        ),
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T17:00:00Z")

    exit_code = main(
        ["accept", "--root", str(root), "--workspace", "Task Space", "--id", record_id]
    )
    captured = capsys.readouterr()

    assert exit_code == 4
    assert "strong duplicates" in captured.err
    assert len(list_workspace_records(config, "inbox")) == 1
    assert len(list_workspace_records(config, "canon")) == 1


def test_rejected_candidates_do_not_enter_canon(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "mem-root"
    record_id = capture_candidate(
        root,
        monkeypatch,
        summary="Status update: migration complete.",
        details="Temporary update for today only.",
        timestamp="2026-04-08T15:30:00Z",
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T16:00:00Z")
    assert main(["score", "--root", str(root), "--workspace", "Task Space", "--id", record_id]) == 0
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-08T17:00:00Z")

    exit_code = main(
        ["accept", "--root", str(root), "--workspace", "Task Space", "--id", record_id]
    )
    captured = capsys.readouterr()
    config = build_config(root=root, workspace="Task Space", env={})

    assert exit_code == 4
    assert "rejected" in captured.err.lower()
    assert list_workspace_records(config, "canon") == []
    assert len(list_workspace_records(config, "inbox")) == 1


def capture_candidate(
    root: Path,
    monkeypatch,
    *,
    summary: str,
    details: str,
    timestamp: str,
) -> str:
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", timestamp)
    exit_code = main(
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

    assert exit_code == 0
    return workspace_inbox_record(root).id


def workspace_inbox_record(root: Path) -> MemoryRecord:
    config = build_config(root=root, workspace="Task Space", env={})
    inbox_records = list_workspace_records(config, "inbox")
    assert len(inbox_records) == 1
    return read_record(inbox_records[0])
