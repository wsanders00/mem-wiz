from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from memwiz.cli import main
from memwiz.config import MemwizConfig, build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score
from memwiz.serde import write_record
from memwiz.storage import initialize_root
from memwiz.validation import run_lint


def _remove_summary(payload: dict) -> None:
    payload.pop("summary")


def _invalidate_id(payload: dict) -> None:
    payload["id"] = "not-an-id"


def _reverse_timestamps(payload: dict) -> None:
    payload["created_at"] = "2026-04-08T16:30:00Z"
    payload["updated_at"] = "2026-04-08T15:30:00Z"


def _remove_accepted_retain_score(payload: dict) -> None:
    payload["score"].pop("retain")


def _remove_archive_reason(payload: dict) -> None:
    payload["decision"].pop("archive_reason")


def test_run_lint_returns_no_findings_for_clean_selected_workspace_and_global_records(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    write_record(
        config.workspace_inbox / "mem_20260408_aaa11111.yaml",
        make_record(
            "mem_20260408_aaa11111",
            scope="workspace",
            workspace=config.workspace_slug,
            status="captured",
        ),
    )
    write_record(
        config.workspace_canon / "mem_20260408_bbb22222.yaml",
        make_record(
            "mem_20260408_bbb22222",
            scope="workspace",
            workspace=config.workspace_slug,
            status="accepted",
        ),
    )
    write_record(
        config.workspace_archive / "mem_20260408_ccc33333.yaml",
        make_record(
            "mem_20260408_ccc33333",
            scope="workspace",
            workspace=config.workspace_slug,
            status="archived",
        ),
    )
    write_record(
        config.global_canon / "mem_20260408_ddd44444.yaml",
        make_record(
            "mem_20260408_ddd44444",
            scope="global",
            workspace=None,
            status="accepted",
        ),
    )
    write_record(
        config.global_archive / "mem_20260408_eee55555.yaml",
        make_record(
            "mem_20260408_eee55555",
            scope="global",
            workspace=None,
            status="archived",
        ),
    )

    findings = run_lint(config, scope="all")

    assert findings == []


def test_run_lint_reports_record_decode_for_corrupt_workspace_inbox_yaml(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    path = config.workspace_inbox / "mem_20260408_aaa11111.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{\n", encoding="utf-8")

    findings = run_lint(config, scope="workspace")

    assert [(finding.level, finding.code, finding.subject) for finding in findings] == [
        ("error", "record-decode", str(path))
    ]


@pytest.mark.parametrize(
    ("mutator", "expected_snippet"),
    [
        (_remove_summary, "summary"),
        (_invalidate_id, "id must match"),
        (_reverse_timestamps, "updated_at must not precede created_at"),
    ],
)
def test_run_lint_reports_record_invalid_for_model_validation_failures(
    tmp_path: Path,
    mutator,
    expected_snippet: str,
) -> None:
    config = make_config(tmp_path)
    path = config.workspace_inbox / "mem_20260408_aaa11111.yaml"
    payload = make_record(
        "mem_20260408_aaa11111",
        scope="workspace",
        workspace=config.workspace_slug,
        status="captured",
    ).to_dict()
    mutator(payload)
    write_payload(path, payload)

    findings = run_lint(config, scope="workspace")

    assert len(findings) == 1
    assert findings[0].code == "record-invalid"
    assert findings[0].subject == str(path)
    assert expected_snippet in findings[0].message


def test_run_lint_reports_record_path_mismatch_for_misnamed_archive_record(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    record = make_record(
        "mem_20260408_aaa11111",
        scope="workspace",
        workspace=config.workspace_slug,
        status="archived",
    )
    path = config.workspace_archive / "mem_20260408_bbb22222.yaml"
    write_record(path, record)

    findings = run_lint(config, scope="workspace")

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("record-path-mismatch", str(path))
    ]


def test_run_lint_reports_record_invalid_for_workspace_canon_status_mismatch(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    path = config.workspace_canon / "mem_20260408_aaa11111.yaml"
    write_record(
        path,
        make_record(
            "mem_20260408_aaa11111",
            scope="workspace",
            workspace=config.workspace_slug,
            status="captured",
        ),
    )

    findings = run_lint(config, scope="workspace")

    assert len(findings) == 1
    assert findings[0].code == "record-invalid"
    assert findings[0].subject == str(path)
    assert "workspace canon record must be accepted, got captured" in findings[0].message


@pytest.mark.parametrize(
    ("path_builder", "payload_mutator", "expected_snippet"),
    [
        (
            lambda config: config.workspace_canon / "mem_20260408_aaa11111.yaml",
            _remove_accepted_retain_score,
            "missing required score fields: score.retain",
        ),
        (
            lambda config: config.workspace_archive / "mem_20260408_bbb22222.yaml",
            _remove_archive_reason,
            "archived records require decision.archive_reason",
        ),
    ],
)
def test_run_lint_reports_record_invalid_for_lifecycle_metadata_failures(
    tmp_path: Path,
    path_builder,
    payload_mutator,
    expected_snippet: str,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    path = path_builder(config)
    status = "accepted" if path.parent.name == "canon" else "archived"
    payload = make_record(
        path.stem,
        scope="workspace",
        workspace=config.workspace_slug,
        status=status,
    ).to_dict()
    payload_mutator(payload)
    write_payload(path, payload)

    findings = run_lint(config, scope="workspace")

    assert len(findings) == 1
    assert findings[0].code == "record-invalid"
    assert findings[0].subject == str(path)
    assert expected_snippet in findings[0].message


def test_run_lint_reports_record_invalid_for_missing_global_provenance(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    path = config.global_canon / "mem_20260408_aaa11111.yaml"
    payload = make_record(
        "mem_20260408_aaa11111",
        scope="global",
        workspace=None,
        status="accepted",
    ).to_dict()
    payload.pop("provenance")
    write_payload(path, payload)

    findings = run_lint(config, scope="global")

    assert len(findings) == 1
    assert findings[0].code == "record-invalid"
    assert findings[0].subject == str(path)
    assert "global records require provenance" in findings[0].message


def test_run_lint_reports_secret_like_content_in_selected_scope(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    path = config.workspace_canon / "mem_20260408_aaa11111.yaml"
    write_record(
        path,
        make_record(
            "mem_20260408_aaa11111",
            scope="workspace",
            workspace=config.workspace_slug,
            status="accepted",
            details="client_secret=abcdefghijklmnop",
        ),
    )

    findings = run_lint(config, scope="workspace")

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("secret-like-content", str(path))
    ]


def test_run_lint_reports_duplicate_conflict_for_workspace_canon_loser(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    winner = make_record(
        "mem_20260408_bbb22222",
        scope="workspace",
        workspace=config.workspace_slug,
        status="accepted",
        summary="Keep lint results deterministic.",
        evidence_score=1.0,
    )
    loser = make_record(
        "mem_20260408_aaa11111",
        scope="workspace",
        workspace=config.workspace_slug,
        status="accepted",
        summary="Keep lint results deterministic!",
        evidence_score=0.5,
    )
    write_record(config.workspace_canon / f"{winner.id}.yaml", winner)
    write_record(config.workspace_canon / f"{loser.id}.yaml", loser)

    findings = run_lint(config, scope="workspace")

    assert len(findings) == 1
    assert findings[0].code == "duplicate-conflict"
    assert findings[0].subject == str(config.workspace_canon / f"{loser.id}.yaml")
    assert winner.id in findings[0].message


def test_run_lint_reports_broken_supersedes_reference(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    path = config.workspace_canon / "mem_20260408_aaa11111.yaml"
    write_record(
        path,
        make_record(
            "mem_20260408_aaa11111",
            scope="workspace",
            workspace=config.workspace_slug,
            status="accepted",
            supersedes="mem_20260408_deadbeef",
        ),
    )

    findings = run_lint(config, scope="workspace")

    assert len(findings) == 1
    assert findings[0].code == "supersedes-invalid"
    assert findings[0].subject == str(path)
    assert "does not resolve" in findings[0].message


def test_run_lint_reports_self_referential_supersedes_reference(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    record = make_record(
        "mem_20260408_aaa11111",
        scope="workspace",
        workspace=config.workspace_slug,
        status="accepted",
        supersedes="mem_20260408_aaa11111",
    )
    path = config.workspace_canon / f"{record.id}.yaml"
    write_record(path, record)

    findings = run_lint(config, scope="workspace")

    assert len(findings) == 1
    assert findings[0].code == "supersedes-invalid"
    assert findings[0].subject == str(path)
    assert "must not reference the same record id" in findings[0].message


def test_run_lint_scope_all_ignores_non_selected_workspace_records(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    other_path = (
        config.root
        / "workspaces"
        / "beta"
        / "canon"
        / "mem_20260408_aaa11111.yaml"
    )
    other_path.parent.mkdir(parents=True, exist_ok=True)
    other_path.write_text("{\n", encoding="utf-8")

    findings = run_lint(config, scope="all")

    assert findings == []


def test_run_lint_orders_tree_findings_before_cross_record_findings(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    workspace_invalid_path = config.workspace_inbox / "mem_20260408_aaa11111.yaml"
    payload = make_record(
        "mem_20260408_aaa11111",
        scope="workspace",
        workspace=config.workspace_slug,
        status="captured",
    ).to_dict()
    payload.pop("summary")
    write_payload(workspace_invalid_path, payload)

    global_secret = make_record(
        "mem_20260408_bbb22222",
        scope="global",
        workspace=None,
        status="accepted",
        details="api_key=abcdefghijklmnop",
    )
    global_secret_path = config.global_canon / f"{global_secret.id}.yaml"
    write_record(global_secret_path, global_secret)

    workspace_winner = make_record(
        "mem_20260408_ddd44444",
        scope="workspace",
        workspace=config.workspace_slug,
        status="accepted",
        summary="Order lint outputs deterministically.",
        evidence_score=1.0,
    )
    workspace_loser = make_record(
        "mem_20260408_ccc33333",
        scope="workspace",
        workspace=config.workspace_slug,
        status="accepted",
        summary="Order lint outputs deterministically!",
        evidence_score=0.5,
    )
    write_record(config.workspace_canon / f"{workspace_winner.id}.yaml", workspace_winner)
    write_record(config.workspace_canon / f"{workspace_loser.id}.yaml", workspace_loser)

    global_broken = make_record(
        "mem_20260408_eee55555",
        scope="global",
        workspace=None,
        status="accepted",
        summary="Broken supersedes references should be reported separately.",
        supersedes="mem_20260408_deadbeef",
        source_memory_id="mem_20260408_dead1111",
    )
    global_broken_path = config.global_canon / f"{global_broken.id}.yaml"
    write_record(global_broken_path, global_broken)

    findings = run_lint(config, scope="all")

    assert [(finding.code, finding.subject) for finding in findings] == [
        ("record-invalid", str(workspace_invalid_path)),
        ("secret-like-content", str(global_secret_path)),
        ("duplicate-conflict", str(config.workspace_canon / f"{workspace_loser.id}.yaml")),
        ("supersedes-invalid", str(global_broken_path)),
    ]


def test_lint_command_returns_zero_with_exact_no_findings_message(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)

    exit_code = main(
        [
            "lint",
            "--root",
            str(config.root),
            "--workspace",
            config.workspace_slug,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "No lint findings.\n"
    assert captured.err == ""


def test_lint_command_prints_findings_as_tab_separated_rows_and_returns_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    path = config.workspace_canon / "mem_20260408_aaa11111.yaml"
    write_record(
        path,
        make_record(
            "mem_20260408_aaa11111",
            scope="workspace",
            workspace=config.workspace_slug,
            status="accepted",
            details="client_secret=abcdefghijklmnop",
        ),
    )

    exit_code = main(
        [
            "lint",
            "--root",
            str(config.root),
            "--workspace",
            config.workspace_slug,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == (
        f"error\tsecret-like-content\t{path}\t"
        "secret-like content detected in managed memory\n"
    )
    assert captured.err == ""


def test_lint_command_defaults_to_workspace_scope(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    initialize_root(config)
    workspace_path = config.workspace_canon / "mem_20260408_aaa11111.yaml"
    global_path = config.global_canon / "mem_20260408_bbb22222.yaml"
    write_record(
        workspace_path,
        make_record(
            "mem_20260408_aaa11111",
            scope="workspace",
            workspace=config.workspace_slug,
            status="accepted",
            details="client_secret=abcdefghijklmnop",
        ),
    )
    write_record(
        global_path,
        make_record(
            "mem_20260408_bbb22222",
            scope="global",
            workspace=None,
            status="accepted",
            details="client_secret=abcdefghijklmnop",
            source_memory_id="mem_20260408_dead1111",
        ),
    )

    exit_code = main(
        [
            "lint",
            "--root",
            str(config.root),
            "--workspace",
            config.workspace_slug,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == (
        f"error\tsecret-like-content\t{workspace_path}\t"
        "secret-like content detected in managed memory\n"
    )
    assert captured.err == ""


def make_config(tmp_path: Path) -> MemwizConfig:
    return build_config(root=tmp_path / "mem-root", workspace="alpha", env={})


def make_record(
    record_id: str,
    *,
    scope: str,
    workspace: str | None,
    status: str,
    summary: str = "Lint records should remain valid and deterministic.",
    details: str | None = "Details help exercise lint coverage.",
    supersedes: str | None = None,
    evidence_score: float = 1.0,
    created_at: str = "2026-04-08T15:30:00Z",
    updated_at: str = "2026-04-08T15:30:00Z",
    source_memory_id: str = "mem_20260408_c0ffee00",
) -> MemoryRecord:
    score = None
    decision = None
    score_reasons = None

    if status != "captured":
        score = Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=evidence_score,
            novelty=0.75,
            scope_fit=1.0,
            retain=0.95,
            promote=0.9 if scope == "global" else None,
        )
        decision = Decision(
            accepted_at=created_at,
            archived_at="2026-04-08T16:30:00Z" if status == "archived" else None,
            archive_reason="retired-by-lint-test" if status == "archived" else None,
        )
        score_reasons = ["durable", "evidence-backed"]

    provenance = None
    if scope == "global":
        provenance = Provenance(
            source_scope="workspace",
            source_workspace="alpha",
            source_memory_id=source_memory_id,
            promoted_at=created_at,
            promotion_reason="Useful across future sessions.",
        )

    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope=scope,
        workspace=workspace,
        kind="workflow",
        summary=summary,
        details=details,
        evidence=[
            EvidenceItem(
                source="conversation",
                ref="turn:user:lint",
                note="validation fixture",
            )
        ],
        confidence="high" if status != "captured" else "medium",
        score=score,
        status=status,
        tags=["lint"],
        decision=decision,
        score_reasons=score_reasons,
        supersedes=supersedes,
        provenance=provenance,
        created_at=created_at,
        updated_at=updated_at,
    )


def write_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
