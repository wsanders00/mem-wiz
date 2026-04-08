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


def test_memwiz_help_lists_top_level_commands(run_memwiz) -> None:
    result = run_memwiz("--help")

    assert result.returncode == 0

    help_output = result.stdout

    for command in TOP_LEVEL_COMMANDS:
        assert command in help_output
