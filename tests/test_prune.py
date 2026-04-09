from __future__ import annotations

import os
from pathlib import Path

import pytest

from memwiz.cli import main
from memwiz.clock import CommandClock
from memwiz.config import MemwizConfig, build_config
from memwiz.fsops import LOCK_FILENAME
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score
from memwiz.pruning import PruneAction, apply_prune_plan, plan_prune
from memwiz.retrieval import CanonDecodeError, CanonValidationError
from memwiz.serde import dump_record, read_record
from memwiz.storage import write_global_canon, write_workspace_canon


def test_plan_prune_returns_no_actions_for_empty_canon(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    assert plan_prune(config, scope="workspace") == []
    assert plan_prune(config, scope="global") == []
    assert plan_prune(config, scope="all") == []


def test_plan_prune_marks_workspace_duplicate_losers_by_kept_winner_id(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Keep accepted workspace canon records sorted.",
        evidence_score=1.0,
    )
    loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Keep accepted workspace canon records sorted!",
        evidence_score=0.5,
    )
    write_workspace_canon(config, winner)
    write_workspace_canon(config, loser)

    actions = plan_prune(config, scope="workspace")

    assert actions == [
        PruneAction(
            record=loser,
            scope="workspace",
            workspace_label=config.workspace_slug,
            reason=f"strong-duplicate-of:{winner.id}",
        )
    ]


def test_plan_prune_marks_global_duplicate_losers_by_kept_winner_id(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    winner = accepted_global_record(
        "mem_20260408_bbb22222",
        summary="Global guidance for pruning duplicate records.",
        source_memory_id="mem_20260408_c0ffee00",
        evidence_score=1.0,
    )
    loser = accepted_global_record(
        "mem_20260408_aaa11111",
        summary="Global guidance for pruning duplicate records!",
        source_memory_id="mem_20260408_deadbeef",
        evidence_score=0.5,
    )
    write_global_canon(config, winner)
    write_global_canon(config, loser)

    actions = plan_prune(config, scope="global")

    assert actions == [
        PruneAction(
            record=loser,
            scope="global",
            workspace_label="-",
            reason=f"strong-duplicate-of:{winner.id}",
        )
    ]


def test_plan_prune_keeps_non_transitive_global_duplicate_chain_members(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    winner = accepted_global_record(
        "mem_20260408_aaa11111",
        summary="Global duplicate baseline summary.",
        source_memory_id="mem_20260408_1111aaaa",
        evidence_score=1.0,
    )
    bridge = accepted_global_record(
        "mem_20260408_bbb22222",
        summary="Global duplicate baseline summary!",
        source_memory_id="mem_20260408_2222bbbb",
        evidence_score=0.5,
    )
    keep = accepted_global_record(
        "mem_20260408_ccc33333",
        summary="Different global memory that only shares provenance with the bridge.",
        source_memory_id="mem_20260408_2222bbbb",
        evidence_score=0.2,
    )
    write_global_canon(config, winner)
    write_global_canon(config, bridge)
    write_global_canon(config, keep)

    actions = plan_prune(config, scope="global")

    assert actions == [
        PruneAction(
            record=bridge,
            scope="global",
            workspace_label="-",
            reason=f"strong-duplicate-of:{winner.id}",
        )
    ]


def test_plan_prune_prioritizes_supersedes_and_excludes_superseded_records_from_duplicate_winner_selection(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    superseded = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Document prune workflow for accepted canon records.",
        evidence_score=1.0,
    )
    successor = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Document prune workflow with updated retention checks.",
        supersedes=superseded.id,
    )
    duplicate_of_superseded = accepted_workspace_record(
        "mem_20260408_ccc33333",
        summary="Document prune workflow for accepted canon records.",
        evidence_score=0.2,
    )
    write_workspace_canon(config, superseded)
    write_workspace_canon(config, successor)
    write_workspace_canon(config, duplicate_of_superseded)

    actions = plan_prune(config, scope="workspace")

    assert actions == [
        PruneAction(
            record=superseded,
            scope="workspace",
            workspace_label=config.workspace_slug,
            reason=f"superseded-by:{successor.id}",
        )
    ]


def test_plan_prune_uses_lexicographically_smallest_successor_id_in_supersede_reason(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    target = accepted_workspace_record("mem_20260408_aaa11111")
    higher = accepted_workspace_record(
        "mem_20260408_ddd44444",
        summary="Newer prune workflow with broad checks.",
        supersedes=target.id,
    )
    lower = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Newer prune workflow with strict checks.",
        supersedes=target.id,
    )
    write_workspace_canon(config, target)
    write_workspace_canon(config, higher)
    write_workspace_canon(config, lower)

    actions = plan_prune(config, scope="workspace")

    assert actions == [
        PruneAction(
            record=target,
            scope="workspace",
            workspace_label=config.workspace_slug,
            reason=f"superseded-by:{lower.id}",
        )
    ]


def test_plan_prune_orders_scope_all_actions_workspace_before_global_then_id(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    workspace_winner = accepted_workspace_record(
        "mem_20260408_ccc33333",
        summary="Workspace duplicate baseline summary.",
        evidence_score=1.0,
    )
    workspace_loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace duplicate baseline summary!",
        evidence_score=0.2,
    )
    global_winner = accepted_global_record(
        "mem_20260408_ddd44444",
        summary="Global duplicate baseline summary.",
        source_memory_id="mem_20260408_1111aaaa",
        evidence_score=1.0,
    )
    global_loser_b = accepted_global_record(
        "mem_20260408_bbb22222",
        summary="Global duplicate baseline summary!",
        source_memory_id="mem_20260408_2222bbbb",
        evidence_score=0.2,
    )
    global_loser_a = accepted_global_record(
        "mem_20260408_aaa00000",
        summary="Global duplicate baseline summary?",
        source_memory_id="mem_20260408_3333cccc",
        evidence_score=0.1,
    )
    write_workspace_canon(config, workspace_winner)
    write_workspace_canon(config, workspace_loser)
    write_global_canon(config, global_winner)
    write_global_canon(config, global_loser_b)
    write_global_canon(config, global_loser_a)

    actions = plan_prune(config, scope="all")

    assert [(action.scope, action.record.id) for action in actions] == [
        ("workspace", workspace_loser.id),
        ("global", global_loser_a.id),
        ("global", global_loser_b.id),
    ]


def test_apply_prune_plan_archives_workspace_and_global_records_with_shared_timestamp(
    tmp_path: Path,
    make_fixed_clock,
) -> None:
    config = make_config(tmp_path)
    workspace_winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Workspace prune winner summary.",
        evidence_score=1.0,
    )
    workspace_loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace prune winner summary!",
        evidence_score=0.1,
    )
    global_winner = accepted_global_record(
        "mem_20260408_ddd44444",
        summary="Global prune winner summary.",
        source_memory_id="mem_20260408_1111aaaa",
        evidence_score=1.0,
    )
    global_loser = accepted_global_record(
        "mem_20260408_ccc33333",
        summary="Global prune winner summary!",
        source_memory_id="mem_20260408_2222bbbb",
        evidence_score=0.1,
    )
    write_workspace_canon(config, workspace_winner)
    write_workspace_canon(config, workspace_loser)
    write_global_canon(config, global_winner)
    write_global_canon(config, global_loser)
    actions = plan_prune(config, scope="all")

    applied = apply_prune_plan(
        config,
        actions,
        command_clock=CommandClock(make_fixed_clock("2026-04-08T16:00:00Z")),
    )

    workspace_archived = read_record(config.workspace_archive / f"{workspace_loser.id}.yaml")
    global_archived = read_record(config.global_archive / f"{global_loser.id}.yaml")

    assert applied == actions
    assert workspace_archived.updated_at == "2026-04-08T16:00:00Z"
    assert global_archived.updated_at == "2026-04-08T16:00:00Z"
    assert workspace_archived.decision is not None
    assert global_archived.decision is not None
    assert workspace_archived.decision.archived_at == "2026-04-08T16:00:00Z"
    assert global_archived.decision.archived_at == "2026-04-08T16:00:00Z"


def test_apply_prune_plan_returns_actions_in_the_original_plan_order(
    tmp_path: Path,
    make_fixed_clock,
) -> None:
    config = make_config(tmp_path)
    workspace_record = accepted_workspace_record("mem_20260408_aaa11111")
    global_record = accepted_global_record("mem_20260408_bbb22222")
    write_workspace_canon(config, workspace_record)
    write_global_canon(config, global_record)
    actions = [
        PruneAction(
            record=global_record,
            scope="global",
            workspace_label="-",
            reason="strong-duplicate-of:mem_20260408_deadbeef",
        ),
        PruneAction(
            record=workspace_record,
            scope="workspace",
            workspace_label=config.workspace_slug,
            reason="superseded-by:mem_20260408_feedface",
        ),
    ]

    applied = apply_prune_plan(
        config,
        actions,
        command_clock=CommandClock(make_fixed_clock("2026-04-08T16:00:00Z")),
    )

    assert applied == actions
    assert (config.global_archive / f"{global_record.id}.yaml").exists()
    assert (config.workspace_archive / f"{workspace_record.id}.yaml").exists()


def test_plan_prune_raises_decode_error_for_corrupt_canon_yaml(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    corrupt_path = config.workspace_canon / "mem_20260408_11111111.yaml"
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text("summary: [broken\n", encoding="utf-8")

    with pytest.raises(CanonDecodeError) as exc_info:
        plan_prune(config, scope="workspace")

    assert exc_info.value.path == corrupt_path
    assert exc_info.value.reason


def test_plan_prune_wraps_schema_invalid_canon_yaml_as_validation_error(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    invalid_path = config.workspace_canon / "mem_20260408_11111111.yaml"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: mem_20260408_11111111",
                "scope: workspace",
                "workspace: mem-wiz",
                "kind: workflow",
                "summary: Schema invalid canon payload",
                "evidence:",
                "  - source: conversation",
                "    ref: turn:user:2026-04-08",
                "status: accepted",
                "score:",
                "  reuse: 1.0",
                "  specificity: 1.0",
                "  durability: 1.0",
                "  evidence: 1.0",
                "  novelty: 0.75",
                "  scope_fit: 1.0",
                "  retain: 1.0",
                "decision:",
                "  accepted_at: 2026-04-08T15:30:00Z",
                "score_reasons:",
                "  - durable",
                "created_at: 2026-04-08T15:30:00Z",
                "updated_at: 2026-04-08T15:30:00Z",
                "unexpected: true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(CanonValidationError) as exc_info:
        plan_prune(config, scope="workspace")

    assert exc_info.value.path == invalid_path
    assert "unexpected keyword argument" in exc_info.value.reason


def test_plan_prune_wraps_invalid_scalar_types_as_validation_error(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    invalid_path = config.workspace_canon / "mem_20260408_22222222.yaml"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: 123",
                "scope: workspace",
                "workspace: mem-wiz",
                "kind: workflow",
                "summary: Schema invalid canon payload",
                "evidence:",
                "  - source: conversation",
                "    ref: turn:user:2026-04-08",
                "status: accepted",
                "score:",
                "  reuse: 1.0",
                "  specificity: 1.0",
                "  durability: 1.0",
                "  evidence: 1.0",
                "  novelty: 0.75",
                "  scope_fit: 1.0",
                "  retain: 1.0",
                "decision:",
                "  accepted_at: 2026-04-08T15:30:00Z",
                "score_reasons:",
                "  - durable",
                "created_at: 2026-04-08T15:30:00Z",
                "updated_at: 2026-04-08T15:30:00Z",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(CanonValidationError) as exc_info:
        plan_prune(config, scope="workspace")

    assert exc_info.value.path == invalid_path
    assert "has no attribute 'strip'" in exc_info.value.reason


def test_plan_prune_raises_validation_error_for_non_accepted_canon_record(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    invalid_record = captured_workspace_record("mem_20260408_11111111")
    invalid_path = config.workspace_canon / f"{invalid_record.id}.yaml"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(dump_record(invalid_record), encoding="utf-8")

    with pytest.raises(CanonValidationError) as exc_info:
        plan_prune(config, scope="workspace")

    assert exc_info.value.path == invalid_path
    assert exc_info.value.reason == "canon record must be accepted, got captured"


def test_prune_command_defaults_to_workspace_scope(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    workspace_winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Workspace prune duplicate summary.",
        evidence_score=1.0,
    )
    workspace_loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace prune duplicate summary!",
        evidence_score=0.1,
    )
    global_winner = accepted_global_record(
        "mem_20260408_ddd44444",
        summary="Global prune duplicate summary.",
        source_memory_id="mem_20260408_deadbeef",
        evidence_score=1.0,
    )
    global_loser = accepted_global_record(
        "mem_20260408_ccc33333",
        summary="Global prune duplicate summary!",
        source_memory_id="mem_20260408_cafefeed",
        evidence_score=0.1,
    )
    write_workspace_canon(config, workspace_winner)
    write_workspace_canon(config, workspace_loser)
    write_global_canon(config, global_winner)
    write_global_canon(config, global_loser)

    result = main(
        [
            "prune",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        "archived\t"
        f"{workspace_loser.id}\tworkspace\tmem-wiz\tstrong-duplicate-of:{workspace_winner.id}\n"
    )
    assert captured.err == ""
    assert not (config.workspace_canon / f"{workspace_loser.id}.yaml").exists()
    assert (config.workspace_archive / f"{workspace_loser.id}.yaml").exists()
    assert (config.global_canon / f"{global_loser.id}.yaml").exists()
    assert not (config.global_archive / f"{global_loser.id}.yaml").exists()


def test_prune_command_scope_global_only_considers_global_canon(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    workspace_winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Workspace prune duplicate summary.",
        evidence_score=1.0,
    )
    workspace_loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace prune duplicate summary!",
        evidence_score=0.1,
    )
    global_winner = accepted_global_record(
        "mem_20260408_ddd44444",
        summary="Global prune duplicate summary.",
        source_memory_id="mem_20260408_deadbeef",
        evidence_score=1.0,
    )
    global_loser = accepted_global_record(
        "mem_20260408_ccc33333",
        summary="Global prune duplicate summary!",
        source_memory_id="mem_20260408_cafefeed",
        evidence_score=0.1,
    )
    write_workspace_canon(config, workspace_winner)
    write_workspace_canon(config, workspace_loser)
    write_global_canon(config, global_winner)
    write_global_canon(config, global_loser)

    result = main(
        [
            "prune",
            "--scope",
            "global",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        f"archived\t{global_loser.id}\tglobal\t-\tstrong-duplicate-of:{global_winner.id}\n"
    )
    assert captured.err == ""
    assert (config.workspace_canon / f"{workspace_loser.id}.yaml").exists()
    assert not (config.workspace_archive / f"{workspace_loser.id}.yaml").exists()
    assert not (config.global_canon / f"{global_loser.id}.yaml").exists()
    assert (config.global_archive / f"{global_loser.id}.yaml").exists()


def test_prune_command_dry_run_prints_would_archive_rows_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Workspace dry-run duplicate summary.",
        evidence_score=1.0,
    )
    loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace dry-run duplicate summary!",
        evidence_score=0.1,
    )
    write_workspace_canon(config, winner)
    write_workspace_canon(config, loser)

    result = main(
        [
            "prune",
            "--dry-run",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        f"would-archive\t{loser.id}\tworkspace\tmem-wiz\tstrong-duplicate-of:{winner.id}\n"
    )
    assert captured.err == ""
    assert (config.workspace_canon / f"{loser.id}.yaml").exists()
    assert not (config.workspace_archive / f"{loser.id}.yaml").exists()


def test_prune_command_apply_prints_archived_rows_and_moves_records(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    workspace_winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Workspace apply duplicate summary.",
        evidence_score=1.0,
    )
    workspace_loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace apply duplicate summary!",
        evidence_score=0.1,
    )
    global_winner = accepted_global_record(
        "mem_20260408_ddd44444",
        summary="Global apply duplicate summary.",
        source_memory_id="mem_20260408_deadbeef",
        evidence_score=1.0,
    )
    global_loser = accepted_global_record(
        "mem_20260408_ccc33333",
        summary="Global apply duplicate summary!",
        source_memory_id="mem_20260408_cafefeed",
        evidence_score=0.1,
    )
    write_workspace_canon(config, workspace_winner)
    write_workspace_canon(config, workspace_loser)
    write_global_canon(config, global_winner)
    write_global_canon(config, global_loser)

    result = main(
        [
            "prune",
            "--scope",
            "all",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        "archived\t"
        f"{workspace_loser.id}\tworkspace\tmem-wiz\tstrong-duplicate-of:{workspace_winner.id}\n"
        f"archived\t{global_loser.id}\tglobal\t-\tstrong-duplicate-of:{global_winner.id}\n"
    )
    assert captured.err == ""
    assert not (config.workspace_canon / f"{workspace_loser.id}.yaml").exists()
    assert (config.workspace_archive / f"{workspace_loser.id}.yaml").exists()
    assert not (config.global_canon / f"{global_loser.id}.yaml").exists()
    assert (config.global_archive / f"{global_loser.id}.yaml").exists()


def test_prune_command_returns_zero_with_exact_noop_message(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)

    result = main(
        [
            "prune",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == "No prune-eligible memories found.\n"
    assert captured.err == ""


def test_prune_command_returns_five_for_canon_decode_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    corrupt_path = config.workspace_canon / "mem_20260408_11111111.yaml"
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text("summary: [broken\n", encoding="utf-8")

    result = main(
        [
            "prune",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 5
    assert captured.out == ""
    assert str(corrupt_path) in captured.err
    assert captured.err.endswith("\n")


def test_prune_command_returns_five_for_invalid_canon_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    invalid_record = captured_workspace_record("mem_20260408_11111111")
    invalid_path = config.workspace_canon / f"{invalid_record.id}.yaml"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(dump_record(invalid_record), encoding="utf-8")

    result = main(
        [
            "prune",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 5
    assert captured.out == ""
    assert captured.err == (
        f"{invalid_path}: canon record must be accepted, got captured\n"
    )


def test_prune_command_returns_six_when_root_lock_is_unavailable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    config.root.mkdir(parents=True, exist_ok=True)
    lock_path = config.root / LOCK_FILENAME
    lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    result = main(
        [
            "prune",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 6
    assert captured.out == ""
    assert str(lock_path) in captured.err


def test_prune_command_scope_all_preflights_both_scopes_before_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    workspace_winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Workspace preflight duplicate summary.",
        evidence_score=1.0,
    )
    workspace_loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace preflight duplicate summary!",
        evidence_score=0.1,
    )
    write_workspace_canon(config, workspace_winner)
    write_workspace_canon(config, workspace_loser)
    corrupt_global_path = config.global_canon / "mem_20260408_99999999.yaml"
    corrupt_global_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_global_path.write_text("summary: [broken\n", encoding="utf-8")

    result = main(
        [
            "prune",
            "--scope",
            "all",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 5
    assert captured.out == ""
    assert str(corrupt_global_path) in captured.err
    assert (config.workspace_canon / f"{workspace_loser.id}.yaml").exists()
    assert not (config.workspace_archive / f"{workspace_loser.id}.yaml").exists()
    assert not any(config.global_archive.glob("*.yaml"))


def test_prune_command_returns_one_for_unexpected_apply_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Workspace failure duplicate summary.",
        evidence_score=1.0,
    )
    loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace failure duplicate summary!",
        evidence_score=0.1,
    )
    write_workspace_canon(config, winner)
    write_workspace_canon(config, loser)

    def raise_unexpected_failure(*_args, **_kwargs):
        raise RuntimeError("simulated apply failure")

    monkeypatch.setattr(
        "memwiz.commands.prune.apply_prune_plan",
        raise_unexpected_failure,
    )

    result = main(
        [
            "prune",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "Prune failed: simulated apply failure\n"
    assert (config.workspace_canon / f"{loser.id}.yaml").exists()
    assert not (config.workspace_archive / f"{loser.id}.yaml").exists()


def test_prune_command_returns_five_for_apply_phase_canon_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    winner = accepted_workspace_record(
        "mem_20260408_bbb22222",
        summary="Workspace failure duplicate summary.",
        evidence_score=1.0,
    )
    loser = accepted_workspace_record(
        "mem_20260408_aaa11111",
        summary="Workspace failure duplicate summary!",
        evidence_score=0.1,
    )
    write_workspace_canon(config, winner)
    write_workspace_canon(config, loser)

    def raise_canon_failure(*_args, **_kwargs):
        raise CanonDecodeError(Path("/tmp/corrupt.yaml"), "simulated decode failure")

    monkeypatch.setattr(
        "memwiz.commands.prune.apply_prune_plan",
        raise_canon_failure,
    )

    result = main(
        [
            "prune",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 5
    assert captured.out == ""
    assert captured.err == "/tmp/corrupt.yaml: simulated decode failure\n"
    assert (config.workspace_canon / f"{loser.id}.yaml").exists()
    assert not (config.workspace_archive / f"{loser.id}.yaml").exists()


def make_config(tmp_path: Path) -> MemwizConfig:
    return build_config(root=tmp_path / "mem-root", workspace="mem-wiz", env={})


def accepted_workspace_record(
    record_id: str,
    *,
    summary: str = "Workspace prune canonical summary.",
    evidence_score: float = 1.0,
    updated_at: str = "2026-04-08T15:30:00Z",
    supersedes: str | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="workspace",
        workspace="mem-wiz",
        kind="workflow",
        summary=summary,
        details="Workspace pruning behavior should remain deterministic.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=evidence_score,
            novelty=0.75,
            scope_fit=1.0,
            retain=1.0,
        ),
        status="accepted",
        tags=["prune"],
        decision=Decision(accepted_at="2026-04-08T15:30:00Z"),
        score_reasons=["durable", "evidence-backed"],
        supersedes=supersedes,
        provenance=None,
        created_at="2026-04-08T15:30:00Z",
        updated_at=updated_at,
    )


def captured_workspace_record(
    record_id: str,
    *,
    summary: str = "Workspace prune draft summary.",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="workspace",
        workspace="mem-wiz",
        kind="workflow",
        summary=summary,
        details=None,
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        confidence="medium",
        score=None,
        status="captured",
        tags=["prune"],
        decision=None,
        score_reasons=None,
        supersedes=None,
        provenance=None,
        created_at="2026-04-08T15:30:00Z",
        updated_at="2026-04-08T15:30:00Z",
    )


def accepted_global_record(
    record_id: str,
    *,
    summary: str = "Global prune canonical summary.",
    source_memory_id: str = "mem_20260408_abc123ef",
    evidence_score: float = 1.0,
    updated_at: str = "2026-04-08T15:30:00Z",
    supersedes: str | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="global",
        workspace=None,
        kind="workflow",
        summary=summary,
        details="Global pruning behavior should remain deterministic.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=evidence_score,
            novelty=0.75,
            scope_fit=1.0,
            retain=1.0,
            promote=0.82,
        ),
        status="accepted",
        tags=["prune"],
        decision=Decision(accepted_at="2026-04-08T15:30:00Z"),
        score_reasons=["durable", "evidence-backed"],
        supersedes=supersedes,
        provenance=Provenance(
            source_scope="workspace",
            source_workspace="mem-wiz",
            source_memory_id=source_memory_id,
            promoted_at="2026-04-08T15:30:00Z",
            promotion_reason="Useful across future repositories.",
        ),
        created_at="2026-04-08T15:30:00Z",
        updated_at=updated_at,
    )
