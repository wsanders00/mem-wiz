from pathlib import Path

from memwiz.config import MemwizConfig, build_config
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score
from memwiz.serde import dump_record
from memwiz.storage import write_global_canon, write_workspace_canon


TOP_LEVEL_COMMANDS = (
    "init",
    "capture",
    "remember",
    "score",
    "accept",
    "promote",
    "lint",
    "compile",
    "search",
    "get",
    "prune",
    "doctor",
    "status",
    "audit",
    "context",
    "self-update",
)


def test_root_invocation_without_args_shows_help(run_memwiz) -> None:
    result = run_memwiz()

    assert result.returncode == 0
    assert "usage:" in result.stdout

    for command in TOP_LEVEL_COMMANDS:
        assert command in result.stdout


def test_root_help_does_not_label_prune_as_placeholder(run_memwiz) -> None:
    result = run_memwiz("--help")

    assert result.returncode == 0
    assert "prune placeholder" not in result.stdout


def test_root_help_does_not_label_doctor_as_placeholder(run_memwiz) -> None:
    result = run_memwiz("--help")

    assert result.returncode == 0
    assert "doctor placeholder" not in result.stdout


def test_root_help_does_not_label_lint_as_placeholder(run_memwiz) -> None:
    result = run_memwiz("--help")

    assert result.returncode == 0
    assert "lint placeholder" not in result.stdout


def test_root_help_does_not_label_compile_as_placeholder(run_memwiz) -> None:
    result = run_memwiz("--help")

    assert result.returncode == 0
    assert "compile placeholder" not in result.stdout


def test_root_help_lists_remember_status_audit_and_context(run_memwiz) -> None:
    result = run_memwiz("--help")

    assert result.returncode == 0

    for command in ("remember", "status", "audit", "context", "self-update"):
        assert command in result.stdout


def test_self_update_help_lists_check_repo_and_format_flags(run_memwiz) -> None:
    result = run_memwiz("self-update", "--help")

    assert result.returncode == 0

    for flag in ("--check", "--repo", "--format", "--root", "--workspace"):
        assert flag in result.stdout


def test_unknown_top_level_command_fails_with_parser_error(run_memwiz) -> None:
    result = run_memwiz("unknown-command")

    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "invalid choice" in result.stderr


def test_capture_help_lists_workspace_flow_flags(run_memwiz) -> None:
    result = run_memwiz("capture", "--help")

    assert result.returncode == 0

    for flag in (
        "--root",
        "--workspace",
        "--kind",
        "--summary",
        "--details",
        "--tag",
        "--evidence-source",
        "--evidence-ref",
    ):
        assert flag in result.stdout


def test_remember_help_lists_policy_and_format_flags(run_memwiz) -> None:
    result = run_memwiz("remember", "--help")

    assert result.returncode == 0

    for flag in (
        "--root",
        "--workspace",
        "--kind",
        "--summary",
        "--details",
        "--tag",
        "--evidence-source",
        "--evidence-ref",
        "--actor-name",
        "--policy-profile",
        "--format",
    ):
        assert flag in result.stdout


def test_score_accept_and_promote_help_include_id_flag(run_memwiz) -> None:
    for command in ("score", "accept", "promote"):
        result = run_memwiz(command, "--help")

        assert result.returncode == 0
        assert "--id" in result.stdout
        assert "--root" in result.stdout
        assert "--workspace" in result.stdout


def test_stateful_commands_reject_malformed_ids_without_tracebacks(
    run_memwiz,
    tmp_path,
) -> None:
    for command in ("score", "accept", "promote"):
        result = run_memwiz(
            command,
            "--root",
            str(tmp_path),
            "--workspace",
            "Task Space",
            "--id",
            "not-an-id",
        )

        assert result.returncode == 2
        assert "invalid memory id" in result.stderr.lower()
        assert "traceback" not in result.stderr.lower()


def test_search_requires_query_with_parser_error(run_memwiz) -> None:
    result = run_memwiz("search")

    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "the following arguments are required: query" in result.stderr


def test_search_help_lists_query_scope_limit_and_shared_flags(run_memwiz) -> None:
    result = run_memwiz("search", "--help")

    assert result.returncode == 0

    for flag in ("query", "--scope", "--limit", "--format", "--root", "--workspace"):
        assert flag in result.stdout


def test_search_rejects_non_positive_limit_with_parser_error(run_memwiz) -> None:
    result = run_memwiz("search", "workflow", "--limit", "0")

    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "limit must be a positive integer" in result.stderr


def test_get_requires_id_flag(run_memwiz) -> None:
    result = run_memwiz("get")

    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "the following arguments are required: --id" in result.stderr


def test_get_help_lists_id_scope_and_shared_flags(run_memwiz) -> None:
    result = run_memwiz("get", "--help")

    assert result.returncode == 0

    for flag in ("--id", "--scope", "--format", "--root", "--workspace"):
        assert flag in result.stdout


def test_prune_help_lists_scope_dry_run_and_shared_flags(run_memwiz) -> None:
    result = run_memwiz("prune", "--help")

    assert result.returncode == 0

    for flag in ("--scope", "--dry-run", "--root", "--workspace"):
        assert flag in result.stdout


def test_doctor_help_lists_shared_flags_only(run_memwiz) -> None:
    result = run_memwiz("doctor", "--help")

    assert result.returncode == 0

    for flag in ("--root", "--workspace", "--format"):
        assert flag in result.stdout

    for flag in ("--scope", "--dry-run", "--id"):
        assert flag not in result.stdout


def test_lint_help_lists_scope_and_shared_flags(run_memwiz) -> None:
    result = run_memwiz("lint", "--help")

    assert result.returncode == 0

    for flag in ("--scope", "--root", "--workspace"):
        assert flag in result.stdout

    for flag in ("--dry-run", "--id"):
        assert flag not in result.stdout


def test_compile_help_lists_scope_and_shared_flags(run_memwiz) -> None:
    result = run_memwiz("compile", "--help")

    assert result.returncode == 0

    for flag in ("--scope", "--format", "--root", "--workspace"):
        assert flag in result.stdout

    for flag in ("--dry-run", "--id"):
        assert flag not in result.stdout


def test_status_help_lists_format_and_shared_flags(run_memwiz) -> None:
    result = run_memwiz("status", "--help")

    assert result.returncode == 0

    for flag in ("--root", "--workspace", "--format"):
        assert flag in result.stdout


def test_audit_help_lists_filter_flags(run_memwiz) -> None:
    result = run_memwiz("audit", "--help")

    assert result.returncode == 0

    for flag in (
        "--root",
        "--workspace",
        "--day",
        "--outcome",
        "--needs-user",
        "--reason-code",
        "--limit",
        "--format",
    ):
        assert flag in result.stdout


def test_audit_rejects_non_positive_limit_with_parser_error(run_memwiz) -> None:
    result = run_memwiz("audit", "--limit", "0")

    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "limit must be a positive integer" in result.stderr


def test_context_help_lists_scope_and_format_flags(run_memwiz) -> None:
    result = run_memwiz("context", "--help")

    assert result.returncode == 0

    for flag in ("--root", "--workspace", "--scope", "--format"):
        assert flag in result.stdout


def test_search_defaults_to_selected_workspace_plus_global_only(
    run_memwiz,
    tmp_path,
) -> None:
    config = make_config(tmp_path)
    other_config = build_config(root=config.root, workspace="Other Space", env={})
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_11111111",
            workspace="task-space",
            summary="Workflow review guide",
        ),
    )
    write_workspace_canon(
        other_config,
        accepted_workspace_record(
            "mem_20260408_22222222",
            workspace="other-space",
            summary="Workflow review for another workspace",
        ),
    )
    write_global_canon(
        config,
        accepted_global_record(
            "mem_20260408_33333333",
            summary="Workflow review defaults",
        ),
    )

    result = run_memwiz(
        "search",
        "workflow review",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 0
    assert result.stdout == (
        "mem_20260408_11111111\tworkspace\ttask-space\tworkflow\tWorkflow review guide\n"
        "mem_20260408_33333333\tglobal\t-\tworkflow\tWorkflow review defaults\n"
    )
    assert "other-space" not in result.stdout


def test_get_defaults_to_workspace_scope(run_memwiz, tmp_path) -> None:
    config = make_config(tmp_path)
    write_global_canon(
        config,
        accepted_global_record("mem_20260408_11111111"),
    )

    result = run_memwiz(
        "get",
        "--id",
        "mem_20260408_11111111",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 3
    assert result.stdout == ""
    assert result.stderr == "Accepted memory not found: mem_20260408_11111111\n"


def test_lint_defaults_to_workspace_scope(run_memwiz, tmp_path) -> None:
    config = make_config(tmp_path)
    invalid_global = config.global_canon / "mem_20260408_11111111.yaml"
    invalid_global.parent.mkdir(parents=True, exist_ok=True)
    invalid_global.write_text(
        dump_record(
            accepted_workspace_record(
                "mem_20260408_11111111",
                workspace="task-space",
            )
        ),
        encoding="utf-8",
    )

    result = run_memwiz(
        "lint",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 0
    assert result.stdout == "No lint findings.\n"
    assert result.stderr == ""


def test_compile_defaults_to_workspace_scope(run_memwiz, tmp_path) -> None:
    config = make_config(tmp_path)
    write_workspace_canon(
        config,
        accepted_workspace_record("mem_20260408_11111111"),
    )
    invalid_global = config.global_canon / "mem_20260408_deadbeef.yaml"
    invalid_global.parent.mkdir(parents=True, exist_ok=True)
    invalid_global.write_text("summary: [broken\n", encoding="utf-8")

    result = run_memwiz(
        "compile",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 0
    assert result.stdout == (
        f"compiled\tworkspace\ttask-space\t{config.workspace_cache / 'digest.md'}\t1\t0\n"
    )
    assert result.stderr == ""
    assert (config.workspace_cache / "digest.md").exists()
    assert not (config.global_cache / "digest.md").exists()


def test_prune_defaults_to_workspace_scope(run_memwiz, tmp_path) -> None:
    config = make_config(tmp_path)
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_bbb22222",
            summary="Workspace duplicate baseline summary.",
            evidence_score=1.0,
        ),
    )
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_aaa11111",
            summary="Workspace duplicate baseline summary!",
            evidence_score=0.1,
        ),
    )
    write_global_canon(
        config,
        accepted_global_record(
            "mem_20260408_ddd44444",
            summary="Global duplicate baseline summary.",
            source_memory_id="mem_20260408_deadbeef",
            evidence_score=1.0,
        ),
    )
    write_global_canon(
        config,
        accepted_global_record(
            "mem_20260408_ccc33333",
            summary="Global duplicate baseline summary!",
            source_memory_id="mem_20260408_cafefeed",
            evidence_score=0.1,
        ),
    )

    result = run_memwiz(
        "prune",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 0
    assert result.stdout == (
        "archived\t"
        "mem_20260408_aaa11111\tworkspace\ttask-space\tstrong-duplicate-of:mem_20260408_bbb22222\n"
    )
    assert result.stderr == ""
    assert (config.workspace_archive / "mem_20260408_aaa11111.yaml").exists()
    assert (config.global_canon / "mem_20260408_ccc33333.yaml").exists()


def test_scope_all_is_limited_to_selected_workspace_plus_global(
    run_memwiz,
    tmp_path,
) -> None:
    config = make_config(tmp_path)
    other_config = build_config(root=config.root, workspace="Other Space", env={})
    write_workspace_canon(
        config,
        accepted_workspace_record("mem_20260408_11111111"),
    )
    write_global_canon(
        config,
        accepted_global_record("mem_20260408_22222222"),
    )
    invalid_other = other_config.workspace_canon / "mem_20260408_33333333.yaml"
    invalid_other.parent.mkdir(parents=True, exist_ok=True)
    invalid_other.write_text("summary: [broken\n", encoding="utf-8")

    result = run_memwiz(
        "lint",
        "--scope",
        "all",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 0
    assert result.stdout == "No lint findings.\n"
    assert result.stderr == ""


def test_lint_scope_all_fails_when_either_selected_scope_has_findings(
    run_memwiz,
    tmp_path,
) -> None:
    config = make_config(tmp_path)
    write_workspace_canon(
        config,
        accepted_workspace_record("mem_20260408_11111111"),
    )
    invalid_global = config.global_canon / "mem_20260408_deadbeef.yaml"
    invalid_global.parent.mkdir(parents=True, exist_ok=True)
    invalid_global.write_text("summary: [broken\n", encoding="utf-8")

    result = run_memwiz(
        "lint",
        "--scope",
        "all",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 2
    assert str(invalid_global) in result.stdout
    assert result.stderr == ""


def test_compile_scope_all_is_all_or_nothing(run_memwiz, tmp_path) -> None:
    config = make_config(tmp_path)
    write_workspace_canon(
        config,
        accepted_workspace_record("mem_20260408_11111111"),
    )
    invalid_global = config.global_canon / "mem_20260408_deadbeef.yaml"
    invalid_global.parent.mkdir(parents=True, exist_ok=True)
    invalid_global.write_text("summary: [broken\n", encoding="utf-8")

    result = run_memwiz(
        "compile",
        "--scope",
        "all",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert str(invalid_global) in result.stderr
    assert not (config.workspace_cache / "digest.md").exists()
    assert not (config.global_cache / "digest.md").exists()


def test_prune_scope_all_is_atomic(run_memwiz, tmp_path) -> None:
    config = make_config(tmp_path)
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_bbb22222",
            summary="Workspace duplicate baseline summary.",
            evidence_score=1.0,
        ),
    )
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_aaa11111",
            summary="Workspace duplicate baseline summary!",
            evidence_score=0.1,
        ),
    )
    invalid_global = config.global_canon / "mem_20260408_deadbeef.yaml"
    invalid_global.parent.mkdir(parents=True, exist_ok=True)
    invalid_global.write_text("summary: [broken\n", encoding="utf-8")

    result = run_memwiz(
        "prune",
        "--scope",
        "all",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert result.returncode == 5
    assert result.stdout == ""
    assert str(invalid_global) in result.stderr
    assert (config.workspace_canon / "mem_20260408_aaa11111.yaml").exists()
    assert not (config.workspace_archive / "mem_20260408_aaa11111.yaml").exists()


def test_representative_exit_code_mapping_for_one_two_three_and_four(
    run_memwiz,
    tmp_path,
) -> None:
    config = make_config(tmp_path)
    workspace_record = accepted_workspace_record("mem_20260408_11111111")
    global_record = accepted_global_record("mem_20260408_11111111")
    write_workspace_canon(config, workspace_record)
    write_global_canon(config, global_record)

    doctor_result = run_memwiz(
        "doctor",
        "--root",
        str(tmp_path / "missing-root"),
        "--workspace",
        "Task Space",
    )
    invalid_id_result = run_memwiz(
        "get",
        "--id",
        "not-an-id",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )
    missing_id_result = run_memwiz(
        "get",
        "--id",
        "mem_20260408_22222222",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
        "--scope",
        "workspace",
    )
    ambiguity_result = run_memwiz(
        "get",
        "--id",
        "mem_20260408_11111111",
        "--scope",
        "all",
        "--root",
        str(config.root),
        "--workspace",
        "Task Space",
    )

    assert doctor_result.returncode == 1
    assert "root-missing" in doctor_result.stdout
    assert invalid_id_result.returncode == 2
    assert missing_id_result.returncode == 3
    assert ambiguity_result.returncode == 4


def make_config(tmp_path) -> MemwizConfig:
    return build_config(root=tmp_path / "mem-root", workspace="Task Space", env={})


def accepted_workspace_record(
    record_id: str,
    *,
    workspace: str = "task-space",
    summary: str = "Workflow review guide",
    evidence_score: float = 0.8,
    updated_at: str = "2026-04-08T10:00:00Z",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="workspace",
        workspace=workspace,
        kind="workflow",
        summary=summary,
        details="Workflow review details remain durable across sessions.",
        evidence=[EvidenceItem(source="doc", ref="docs/review.md")],
        status="accepted",
        score=Score(
            reuse=0.8,
            specificity=0.8,
            durability=0.8,
            evidence=evidence_score,
            novelty=0.8,
            scope_fit=0.8,
            retain=0.8,
        ),
        tags=["review"],
        decision=Decision(accepted_at="2026-04-08T09:00:00Z"),
        score_reasons=["retain-score:0.80"],
        created_at="2026-04-08T09:00:00Z",
        updated_at=updated_at,
    )


def accepted_global_record(
    record_id: str,
    *,
    summary: str = "Workflow review defaults",
    source_memory_id: str = "mem_20260408_aaaaaaaa",
    evidence_score: float = 0.8,
    updated_at: str = "2026-04-08T10:00:00Z",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="global",
        kind="workflow",
        summary=summary,
        details="Portable review defaults remain useful across repositories.",
        evidence=[EvidenceItem(source="doc", ref="docs/review.md")],
        status="accepted",
        score=Score(
            reuse=0.8,
            specificity=0.8,
            durability=0.8,
            evidence=evidence_score,
            novelty=0.8,
            scope_fit=0.8,
            retain=0.8,
            promote=0.8,
        ),
        tags=["review"],
        decision=Decision(accepted_at="2026-04-08T09:00:00Z"),
        score_reasons=["retain-score:0.80", "promote-score:0.80"],
        provenance=Provenance(
            source_scope="workspace",
            source_workspace="task-space",
            source_memory_id=source_memory_id,
            promoted_at="2026-04-08T09:00:00Z",
            promotion_reason="portable review defaults",
        ),
        created_at="2026-04-08T09:00:00Z",
        updated_at=updated_at,
    )
