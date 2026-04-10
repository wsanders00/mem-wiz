from __future__ import annotations

import json
from pathlib import Path


def test_autonomous_cli_loop_context_remember_status_audit_and_context_json(
    run_memwiz,
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "mem-root"

    init_result = run_memwiz("init", "--root", str(memory_root))
    assert init_result.returncode == 0

    initial_context = run_memwiz(
        "context",
        "--root",
        str(memory_root),
        "--workspace",
        "Task Space",
        "--format",
        "json",
    )
    initial_payload = json.loads(initial_context.stdout)

    assert initial_context.returncode == 0
    assert initial_payload["scope"] == "all"
    assert initial_payload["included_record_ids"] == []
    assert initial_payload["omitted_count"] == 0

    remember_result = run_memwiz(
        "remember",
        "--root",
        str(memory_root),
        "--workspace",
        "Task Space",
        "--kind",
        "workflow",
        "--summary",
        "Run status and audit after autonomous writes.",
        "--details",
        "Check review pressure before handoff.",
        "--evidence-source",
        "doc",
        "--evidence-ref",
        "README.md",
        "--actor-name",
        "codex",
        "--format",
        "json",
        env_overrides={"MEMWIZ_FIXED_NOW": "2026-04-10T12:00:00Z"},
    )
    remember_payload = json.loads(remember_result.stdout)

    assert remember_result.returncode == 0
    assert remember_payload["outcome"] == "auto_accepted"
    assert remember_payload["accepted"] is True
    assert remember_payload["review_required"] is False

    status_result = run_memwiz(
        "status",
        "--root",
        str(memory_root),
        "--workspace",
        "Task Space",
        "--format",
        "json",
    )
    status_payload = json.loads(status_result.stdout)

    assert status_result.returncode == 0
    assert status_payload["counts"]["workspace_inbox"] == 0
    assert status_payload["counts"]["workspace_canon"] == 1
    assert status_payload["counts"]["recent_audit_events"] == 1
    assert status_payload["review_required_count"] == 0

    audit_result = run_memwiz(
        "audit",
        "--root",
        str(memory_root),
        "--workspace",
        "Task Space",
        "--format",
        "json",
    )
    audit_payload = json.loads(audit_result.stdout)

    assert audit_result.returncode == 0
    assert len(audit_payload["events"]) == 1
    assert audit_payload["events"][0]["outcome"] == "auto_accepted"
    assert audit_payload["events"][0]["memory_id"] == remember_payload["memory_id"]

    final_context = run_memwiz(
        "context",
        "--root",
        str(memory_root),
        "--workspace",
        "Task Space",
        "--format",
        "json",
    )
    final_payload = json.loads(final_context.stdout)

    assert final_context.returncode == 0
    assert final_payload["included_record_ids"] == [remember_payload["memory_id"]]
    assert "Run status and audit after autonomous writes." in final_payload["text"]
