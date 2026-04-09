TOP_LEVEL_COMMANDS = (
    "init",
    "capture",
    "score",
    "accept",
    "promote",
    "lint",
    "compile",
    "search",
    "get",
    "prune",
    "doctor",
)


def test_root_invocation_without_args_shows_help(run_memwiz) -> None:
    result = run_memwiz()

    assert result.returncode == 0
    assert "usage:" in result.stdout

    for command in TOP_LEVEL_COMMANDS:
        assert command in result.stdout


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

    for flag in ("query", "--scope", "--limit", "--root", "--workspace"):
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

    for flag in ("--id", "--scope", "--root", "--workspace"):
        assert flag in result.stdout
