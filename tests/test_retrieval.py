from __future__ import annotations

from pathlib import Path

import pytest

from memwiz.cli import main
from memwiz.config import MemwizConfig, build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score
from memwiz.retrieval import (
    AmbiguousMemoryIdError,
    CanonDecodeError,
    CanonValidationError,
    InvalidMemoryIdError,
    InvalidSearchQueryError,
    MemoryNotFoundError,
    get_record,
    search_records,
)
from memwiz.serde import dump_record
from memwiz.storage import write_global_canon, write_workspace_canon


def test_search_records_queries_workspace_and_global_canon_by_default(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    workspace_record = accepted_workspace_record(
        "mem_20260408_11111111",
        summary="Workflow review guide",
    )
    global_record = accepted_global_record(
        "mem_20260408_22222222",
        summary="Workflow review defaults",
    )
    write_workspace_canon(config, workspace_record)
    write_global_canon(config, global_record)

    hits = search_records(config, "workflow review", scope="all", limit=10)

    assert [hit.record.id for hit in hits] == [
        workspace_record.id,
        global_record.id,
    ]
    assert [hit.scope for hit in hits] == ["workspace", "global"]
    assert [hit.workspace_label for hit in hits] == [
        config.workspace_slug,
        "-",
    ]


def test_search_records_applies_scope_filter(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    workspace_record = accepted_workspace_record(
        "mem_20260408_11111111",
        summary="Workflow review guide",
    )
    global_record = accepted_global_record(
        "mem_20260408_22222222",
        summary="Workflow review defaults",
    )
    write_workspace_canon(config, workspace_record)
    write_global_canon(config, global_record)

    workspace_hits = search_records(config, "workflow review", scope="workspace", limit=10)
    global_hits = search_records(config, "workflow review", scope="global", limit=10)

    assert [hit.record.id for hit in workspace_hits] == [workspace_record.id]
    assert [hit.record.id for hit in global_hits] == [global_record.id]


def test_search_records_uses_rank_buckets_then_stable_tiebreaks(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    bucket_three = accepted_workspace_record(
        "mem_20260408_11111111",
        summary="Workflow review checklist",
        updated_at="2026-04-08T12:00:00Z",
    )
    bucket_four = accepted_workspace_record(
        "mem_20260408_22222222",
        summary="Review the workflow after capture",
        updated_at="2026-04-08T12:01:00Z",
    )
    bucket_five_workspace_newer = accepted_workspace_record(
        "mem_20260408_55555555",
        summary="Review retained memories",
        updated_at="2026-04-08T12:05:00Z",
    )
    bucket_five_workspace_a = accepted_workspace_record(
        "mem_20260408_33333333",
        summary="Review retained memories",
        updated_at="2026-04-08T12:03:00Z",
    )
    bucket_five_workspace_b = accepted_workspace_record(
        "mem_20260408_44444444",
        summary="Review retained memories",
        updated_at="2026-04-08T12:03:00Z",
    )
    bucket_five_global = accepted_global_record(
        "mem_20260408_66666666",
        summary="Review retained memories",
        updated_at="2026-04-08T12:06:00Z",
    )
    bucket_six = accepted_workspace_record(
        "mem_20260408_77777777",
        summary="Retained memory defaults",
        details="Workflow review notes live in the audit appendix.",
        updated_at="2026-04-08T12:04:00Z",
    )

    for record in (
        bucket_five_global,
        bucket_five_workspace_b,
        bucket_six,
        bucket_four,
        bucket_five_workspace_newer,
        bucket_three,
        bucket_five_workspace_a,
    ):
        write_record_for_scope(config, record)

    ranked_hits = search_records(config, "workflow review", scope="all", limit=10)
    exact_id_hits = search_records(config, bucket_three.id, scope="all", limit=10)
    prefix_hits = search_records(config, "mem_20260408_11", scope="all", limit=10)

    assert [hit.record.id for hit in ranked_hits] == [
        bucket_three.id,
        bucket_four.id,
        bucket_five_workspace_newer.id,
        bucket_five_workspace_a.id,
        bucket_five_workspace_b.id,
        bucket_five_global.id,
        bucket_six.id,
    ]
    assert [hit.rank_bucket for hit in ranked_hits] == [3, 4, 5, 5, 5, 5, 6]
    assert [hit.record.id for hit in exact_id_hits] == [bucket_three.id]
    assert [hit.rank_bucket for hit in exact_id_hits] == [1]
    assert [hit.record.id for hit in prefix_hits] == [bucket_three.id]
    assert [hit.rank_bucket for hit in prefix_hits] == [2]


def test_search_records_applies_limit_after_full_sorting(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    low_rank = accepted_global_record(
        "mem_20260408_11111111",
        summary="Retained memory defaults",
        details="Workflow review appendix",
    )
    middle_rank = accepted_workspace_record(
        "mem_20260408_22222222",
        summary="Review the workflow after capture",
    )
    top_rank = accepted_workspace_record(
        "mem_20260408_33333333",
        summary="Workflow review checklist",
    )

    for record in (low_rank, middle_rank, top_rank):
        write_record_for_scope(config, record)

    hits = search_records(config, "workflow review", scope="all", limit=2)

    assert [hit.record.id for hit in hits] == [top_rank.id, middle_rank.id]


def test_search_records_rejects_whitespace_only_queries(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(InvalidSearchQueryError):
        search_records(config, "   \t  ", scope="all", limit=10)


def test_search_records_rejects_invalid_scope(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="invalid retrieval scope"):
        search_records(config, "workflow", scope="invalid", limit=10)


def test_search_records_rejects_non_positive_limit(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        search_records(config, "workflow", scope="all", limit=0)


def test_get_record_returns_workspace_record_by_exact_id(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    record = accepted_workspace_record("mem_20260408_11111111")
    write_workspace_canon(config, record)

    resolved = get_record(config, record.id, scope="all")

    assert resolved == record


def test_get_record_returns_global_record_by_exact_id(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    record = accepted_global_record("mem_20260408_11111111")
    write_global_canon(config, record)

    resolved = get_record(config, record.id, scope="all")

    assert resolved == record


def test_get_record_rejects_invalid_memory_id(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(InvalidMemoryIdError, match="invalid memory id"):
        get_record(config, "not-an-id", scope="all")


def test_get_record_raises_not_found_for_missing_id(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(MemoryNotFoundError, match="accepted memory not found"):
        get_record(config, "mem_20260408_11111111", scope="all")


def test_get_record_raises_ambiguity_when_id_exists_in_both_scopes(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    workspace_record = accepted_workspace_record("mem_20260408_11111111")
    global_record = accepted_global_record("mem_20260408_11111111")
    write_workspace_canon(config, workspace_record)
    write_global_canon(config, global_record)

    with pytest.raises(AmbiguousMemoryIdError, match="exists in both workspace and global"):
        get_record(config, workspace_record.id, scope="all")


def test_retrieval_raises_decode_error_for_corrupt_canon_yaml(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    corrupt_path = config.workspace_canon / "mem_20260408_11111111.yaml"
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text("summary: [broken\n", encoding="utf-8")

    with pytest.raises(CanonDecodeError) as exc_info:
        search_records(config, "workflow", scope="all", limit=10)

    assert exc_info.value.path == corrupt_path
    assert exc_info.value.reason
    assert str(corrupt_path) in str(exc_info.value)
    assert exc_info.value.reason in str(exc_info.value)


def test_retrieval_raises_validation_error_for_non_accepted_canon_record(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    invalid_record = captured_workspace_record(
        "mem_20260408_11111111",
        summary="Workflow review draft",
    )
    invalid_path = config.workspace_canon / f"{invalid_record.id}.yaml"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(dump_record(invalid_record), encoding="utf-8")

    with pytest.raises(CanonValidationError) as exc_info:
        search_records(config, "workflow", scope="all", limit=10)

    assert exc_info.value.path == invalid_path
    assert exc_info.value.reason == "canon record must be accepted, got captured"
    assert str(invalid_path) in str(exc_info.value)
    assert exc_info.value.reason in str(exc_info.value)


def test_search_command_prints_tab_separated_rows_for_matches(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    workspace_record = accepted_workspace_record(
        "mem_20260408_11111111",
        summary="Workflow review guide",
    )
    global_record = accepted_global_record(
        "mem_20260408_22222222",
        summary="Workflow review defaults",
    )
    write_workspace_canon(config, workspace_record)
    write_global_canon(config, global_record)

    result = main(
        [
            "search",
            "workflow review",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        f"{workspace_record.id}\tworkspace\ttask-space\tworkflow\tWorkflow review guide\n"
        f"{global_record.id}\tglobal\t-\tworkflow\tWorkflow review defaults\n"
    )
    assert captured.err == ""


def test_search_command_sanitizes_tabs_in_summary_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    record = accepted_workspace_record(
        "mem_20260408_11111111",
        summary="Workflow\treview guide",
    )
    write_workspace_canon(config, record)

    result = main(
        [
            "search",
            "workflow review",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert record.summary == "Workflow\treview guide"
    assert captured.out == (
        f"{record.id}\tworkspace\ttask-space\tworkflow\tWorkflow review guide\n"
    )
    assert captured.err == ""


def test_search_command_respects_scope_and_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    top_workspace = accepted_workspace_record(
        "mem_20260408_11111111",
        summary="Workflow review checklist",
    )
    lower_workspace = accepted_workspace_record(
        "mem_20260408_22222222",
        summary="Review the workflow after capture",
    )
    global_record = accepted_global_record(
        "mem_20260408_33333333",
        summary="Workflow review defaults",
    )

    for record in (lower_workspace, global_record, top_workspace):
        write_record_for_scope(config, record)

    result = main(
        [
            "search",
            "workflow review",
            "--scope",
            "workspace",
            "--limit",
            "1",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        f"{top_workspace.id}\tworkspace\ttask-space\tworkflow\tWorkflow review checklist\n"
    )
    assert captured.err == ""


def test_search_command_returns_zero_with_exact_no_match_message(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)

    result = main(
        [
            "search",
            "workflow review",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == "No accepted memories found.\n"
    assert captured.err == ""


def test_search_command_returns_two_for_whitespace_only_query(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)

    result = main(
        [
            "search",
            "   \t  ",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert captured.err == "Search query cannot be empty.\n"


def test_search_command_returns_five_for_canon_decode_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    corrupt_path = config.workspace_canon / "mem_20260408_11111111.yaml"
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text(
        "schema_version: !!python/object/new:object []\n",
        encoding="utf-8",
    )

    result = main(
        [
            "search",
            "workflow",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 5
    assert captured.out == ""
    assert str(corrupt_path) in captured.err
    assert "could not determine a constructor" in captured.err


def test_search_command_returns_five_for_invalid_canon_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    invalid_record = captured_workspace_record(
        "mem_20260408_11111111",
        summary="Workflow review draft",
    )
    invalid_path = config.workspace_canon / f"{invalid_record.id}.yaml"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(dump_record(invalid_record), encoding="utf-8")

    result = main(
        [
            "search",
            "workflow",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 5
    assert captured.out == ""
    assert captured.err == (
        f"{invalid_path}: canon record must be accepted, got captured\n"
    )


def test_get_command_prints_canonical_yaml_for_workspace_record(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    record = accepted_workspace_record("mem_20260408_11111111")
    write_workspace_canon(config, record)

    result = main(
        [
            "get",
            "--id",
            record.id,
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == dump_record(record)
    assert captured.err == ""


def test_get_command_prints_canonical_yaml_for_global_record(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    record = accepted_global_record("mem_20260408_11111111")
    write_global_canon(config, record)

    result = main(
        [
            "get",
            "--id",
            record.id,
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == dump_record(record)
    assert captured.err == ""


def test_get_command_returns_two_for_invalid_memory_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)

    result = main(
        [
            "get",
            "--id",
            "not-an-id",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert captured.err == "Invalid memory id: not-an-id\n"


def test_get_command_returns_three_for_missing_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)

    result = main(
        [
            "get",
            "--id",
            "mem_20260408_11111111",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 3
    assert captured.out == ""
    assert captured.err == "Accepted memory not found: mem_20260408_11111111\n"


def test_get_command_returns_four_for_cross_scope_ambiguity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    workspace_record = accepted_workspace_record("mem_20260408_11111111")
    global_record = accepted_global_record("mem_20260408_11111111")
    write_workspace_canon(config, workspace_record)
    write_global_canon(config, global_record)

    result = main(
        [
            "get",
            "--id",
            workspace_record.id,
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 4
    assert captured.out == ""
    assert captured.err == (
        "memory id mem_20260408_11111111 exists in both workspace and global; "
        "retry with --scope workspace or --scope global\n"
    )


def test_get_command_returns_five_for_canon_decode_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    corrupt_path = config.workspace_canon / "mem_20260408_11111111.yaml"
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text(
        "schema_version: !!python/object/new:object []\n",
        encoding="utf-8",
    )

    result = main(
        [
            "get",
            "--id",
            "mem_20260408_11111111",
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 5
    assert captured.out == ""
    assert str(corrupt_path) in captured.err
    assert "could not determine a constructor" in captured.err


def test_get_command_returns_five_for_invalid_canon_state(
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
            "get",
            "--id",
            invalid_record.id,
            "--root",
            str(config.root),
            "--workspace",
            "Task Space",
        ]
    )
    captured = capsys.readouterr()

    assert result == 5
    assert captured.out == ""
    assert captured.err == (
        f"{invalid_path}: canon record must be accepted, got captured\n"
    )


def make_config(tmp_path: Path) -> MemwizConfig:
    return build_config(root=tmp_path / "memory-root", workspace="Task Space")


def accepted_workspace_record(
    record_id: str,
    *,
    summary: str = "Workflow review guide",
    details: str | None = None,
    kind: str = "workflow",
    tags: list[str] | None = None,
    created_at: str = "2026-04-08T10:00:00Z",
    updated_at: str = "2026-04-08T10:00:00Z",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="workspace",
        workspace="task-space",
        kind=kind,
        summary=summary,
        details=details,
        evidence=[EvidenceItem(source="doc", ref="docs/retrieval.md", note="workflow review")],
        status="accepted",
        score=Score(
            reuse=0.8,
            specificity=0.8,
            durability=0.8,
            evidence=0.8,
            novelty=0.8,
            scope_fit=0.8,
            retain=0.8,
        ),
        tags=tags or [],
        decision=Decision(accepted_at=updated_at),
        score_reasons=["retain-score:0.80"],
        created_at=created_at,
        updated_at=updated_at,
    )


def accepted_global_record(
    record_id: str,
    *,
    summary: str = "Workflow review guide",
    details: str | None = None,
    kind: str = "workflow",
    tags: list[str] | None = None,
    created_at: str = "2026-04-08T10:00:00Z",
    updated_at: str = "2026-04-08T10:00:00Z",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="global",
        kind=kind,
        summary=summary,
        details=details,
        evidence=[EvidenceItem(source="doc", ref="docs/retrieval.md", note="workflow review")],
        status="accepted",
        score=Score(
            reuse=0.8,
            specificity=0.8,
            durability=0.8,
            evidence=0.8,
            novelty=0.8,
            scope_fit=0.8,
            retain=0.8,
            promote=0.8,
        ),
        tags=tags or [],
        decision=Decision(accepted_at=updated_at),
        score_reasons=["retain-score:0.80", "promote-score:0.80"],
        provenance=Provenance(
            source_scope="workspace",
            source_workspace="task-space",
            source_memory_id="mem_20260401_aaaaaaaa",
            promoted_at=updated_at,
            promotion_reason="portable workflow review guidance",
        ),
        created_at=created_at,
        updated_at=updated_at,
    )


def captured_workspace_record(
    record_id: str,
    *,
    summary: str = "Workflow review draft",
    details: str | None = None,
    kind: str = "workflow",
    tags: list[str] | None = None,
    created_at: str = "2026-04-08T10:00:00Z",
    updated_at: str = "2026-04-08T10:00:00Z",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="workspace",
        workspace="task-space",
        kind=kind,
        summary=summary,
        details=details,
        evidence=[EvidenceItem(source="doc", ref="docs/retrieval.md", note="workflow review")],
        status="captured",
        tags=tags or [],
        created_at=created_at,
        updated_at=updated_at,
    )


def write_record_for_scope(config: MemwizConfig, record: MemoryRecord) -> None:
    if record.scope == "workspace":
        write_workspace_canon(config, record)
        return

    write_global_canon(config, record)
