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
