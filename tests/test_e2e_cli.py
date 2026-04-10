from __future__ import annotations

import re
from pathlib import Path


MEMORY_ID_PATTERN = re.compile(r"mem_\d{8}_[0-9a-f]{8}")


def _run_with_time(run_memwiz, timestamp: str, *args: str):
    return run_memwiz(*args, env_overrides={"MEMWIZ_FIXED_NOW": timestamp})


def _extract_captured_id(output: str) -> str:
    matches = MEMORY_ID_PATTERN.findall(output)
    assert len(matches) == 1
    return matches[0]


def _extract_promoted_id(output: str) -> str:
    matches = MEMORY_ID_PATTERN.findall(output)
    assert len(matches) == 2
    return matches[-1]


def _parse_search_hits(output: str) -> list[list[str]]:
    return [line.split("\t") for line in output.strip().splitlines() if line.strip()]


def test_cli_end_to_end_flow(tmp_path: Path, run_memwiz) -> None:
    memory_root = tmp_path / "mem-root"
    workspace = "Task Space"
    workspace_slug = "task-space"

    init_result = run_memwiz("init", "--root", str(memory_root))
    assert init_result.returncode == 0

    capture_result = _run_with_time(
        run_memwiz,
        "2026-04-08T15:30:00Z",
        "capture",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "--kind",
        "workflow",
        "--summary",
        "Capture durable workflow notes for Task Space.",
        "--details",
        "Workspace candidates land in inbox before scoring.",
        "--evidence-source",
        "conversation",
        "--evidence-ref",
        "turn:user:2026-04-08",
    )
    assert capture_result.returncode == 0
    record_id = _extract_captured_id(capture_result.stdout)

    score_result = _run_with_time(
        run_memwiz,
        "2026-04-08T16:00:00Z",
        "score",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "--id",
        record_id,
    )
    assert score_result.returncode == 0

    accept_result = _run_with_time(
        run_memwiz,
        "2026-04-08T17:00:00Z",
        "accept",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "--id",
        record_id,
    )
    assert accept_result.returncode == 0

    promote_result = _run_with_time(
        run_memwiz,
        "2026-04-08T18:00:00Z",
        "promote",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "--id",
        record_id,
    )
    assert promote_result.returncode == 0
    promoted_id = _extract_promoted_id(promote_result.stdout)
    assert promoted_id != ""

    secret_capture = _run_with_time(
        run_memwiz,
        "2026-04-08T19:00:00Z",
        "capture",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "--kind",
        "workflow",
        "--summary",
        "Store access_token=abcdefghi for later.",
        "--details",
        "This should trigger the secret guard",
        "--evidence-source",
        "conversation",
        "--evidence-ref",
        "turn:user:2026-04-08",
    )
    assert secret_capture.returncode == 4
    assert "secret-like content" in secret_capture.stderr.lower()

    lint_result = run_memwiz(
        "lint",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "--scope",
        "all",
    )
    assert lint_result.returncode == 0
    assert lint_result.stdout.strip() == "No lint findings."

    compile_result = run_memwiz(
        "compile",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "--scope",
        "all",
    )
    assert compile_result.returncode == 0
    assert "compiled\t" in compile_result.stdout

    search_result = run_memwiz(
        "search",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "workflow",
    )
    assert search_result.returncode == 0
    hits = _parse_search_hits(search_result.stdout)
    assert len(hits) == 2
    scopes = {hit[1] for hit in hits}
    assert scopes == {"workspace", "global"}
    workspace_labels = {hit[2] for hit in hits}
    assert workspace_slug in workspace_labels
    assert "-" in workspace_labels

    prune_result = run_memwiz(
        "prune",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
        "--scope",
        "workspace",
        "--dry-run",
    )
    assert prune_result.returncode == 0
    assert "No prune-eligible memories found." in prune_result.stdout

    doctor_result = run_memwiz(
        "doctor",
        "--root",
        str(memory_root),
        "--workspace",
        workspace,
    )
    assert doctor_result.returncode == 0
    assert doctor_result.stdout.strip() == "No doctor findings."
