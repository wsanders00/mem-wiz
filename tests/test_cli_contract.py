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


def test_score_and_accept_help_include_id_flag(run_memwiz) -> None:
    for command in ("score", "accept"):
        result = run_memwiz(command, "--help")

        assert result.returncode == 0
        assert "--id" in result.stdout
        assert "--root" in result.stdout
        assert "--workspace" in result.stdout
