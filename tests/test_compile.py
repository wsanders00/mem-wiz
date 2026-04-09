from __future__ import annotations

import os
from pathlib import Path

import pytest

from memwiz.cli import main
from memwiz.compiler import CompileValidationError, build_digest_plans
from memwiz.config import MemwizConfig, build_config
from memwiz.fsops import LOCK_FILENAME
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score
from memwiz.storage import write_global_canon, write_workspace_canon


def test_build_digest_plans_rejects_corrupt_workspace_canon_yaml(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    corrupt_path = config.workspace_canon / "mem_20260408_deadbeef.yaml"
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text("summary: [broken\n", encoding="utf-8")

    with pytest.raises(CompileValidationError) as exc_info:
        build_digest_plans(
            config,
            scope="workspace",
            generated_at="2026-04-09T12:00:00Z",
        )

    assert exc_info.value.path == corrupt_path
    assert "decode" in exc_info.value.reason.lower()


def test_build_digest_plans_rejects_schema_invalid_workspace_canon_record(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    invalid_path = config.workspace_canon / "mem_20260408_deadbeef.yaml"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "id: mem_20260408_deadbeef",
                "scope: workspace",
                "workspace: mem-wiz",
                "kind: workflow",
                "summary: Accepted canon record missing required score",
                "evidence:",
                "  - source: conversation",
                "    ref: turn:user:2026-04-09",
                "status: accepted",
                "decision:",
                "  accepted_at: 2026-04-09T07:00:00Z",
                "score_reasons:",
                "  - durable",
                "created_at: 2026-04-09T07:00:00Z",
                "updated_at: 2026-04-09T08:00:00Z",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CompileValidationError) as exc_info:
        build_digest_plans(
            config,
            scope="workspace",
            generated_at="2026-04-09T12:00:00Z",
        )

    assert exc_info.value.path == invalid_path
    assert "record failed validation" in exc_info.value.reason


def test_build_digest_plans_rejects_secret_like_workspace_canon_content(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    record = accepted_workspace_record(
        "mem_20260408_deadbeef",
        summary="Bearer sk-secret-token-123456 should never enter digest output.",
    )
    write_workspace_canon(config, record)

    with pytest.raises(CompileValidationError) as exc_info:
        build_digest_plans(
            config,
            scope="workspace",
            generated_at="2026-04-09T12:00:00Z",
        )

    assert exc_info.value.path == config.workspace_canon / f"{record.id}.yaml"
    assert exc_info.value.reason == "secret-like content detected in accepted canon"


def test_build_digest_plans_renders_sections_in_fixed_kind_order(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    for record in (
        accepted_workspace_record(
            "mem_20260408_66666666",
            kind="warning",
            summary="Warning summary",
        ),
        accepted_workspace_record(
            "mem_20260408_11111111",
            kind="preference",
            summary="Preference summary",
        ),
        accepted_workspace_record(
            "mem_20260408_55555555",
            kind="decision",
            summary="Decision summary",
        ),
        accepted_workspace_record(
            "mem_20260408_22222222",
            kind="constraint",
            summary="Constraint summary",
        ),
        accepted_workspace_record(
            "mem_20260408_33333333",
            kind="fact",
            summary="Fact summary",
        ),
        accepted_workspace_record(
            "mem_20260408_44444444",
            kind="workflow",
            summary="Workflow summary",
        ),
    ):
        write_workspace_canon(config, record)

    [plan] = build_digest_plans(
        config,
        scope="workspace",
        generated_at="2026-04-09T12:00:00Z",
    )

    assert plan.scope == "workspace"
    assert plan.workspace_label == "mem-wiz"
    assert plan.path == config.workspace_cache / "digest.md"
    assert plan.included_count == 6
    assert plan.omitted_count == 0
    assert plan.content.startswith(
        "\n".join(
            [
                "# Mem-Wiz Digest",
                "Generated: 2026-04-09T12:00:00Z",
                "Scope: workspace:mem-wiz",
                "Included: 6",
                "Omitted: 0",
                "",
            ]
        )
    )
    assert digest_headings(plan.content) == [
        "## Preferences",
        "## Constraints",
        "## Facts",
        "## Workflows",
        "## Decisions",
        "## Warnings",
    ]


def test_build_digest_plans_orders_records_within_section_by_retain_updated_then_id(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)

    for record in (
        accepted_workspace_record(
            "mem_20260408_33333333",
            kind="fact",
            summary="Highest retain fact",
            retain=0.95,
            updated_at="2026-04-09T09:00:00Z",
        ),
        accepted_workspace_record(
            "mem_20260408_cccccccc",
            kind="fact",
            summary="Newer tied fact",
            retain=0.90,
            updated_at="2026-04-09T11:00:00Z",
        ),
        accepted_workspace_record(
            "mem_20260408_aaaaaaaa",
            kind="fact",
            summary="Same time lower id fact",
            retain=0.90,
            updated_at="2026-04-09T10:00:00Z",
        ),
        accepted_workspace_record(
            "mem_20260408_bbbbbbbb",
            kind="fact",
            summary="Same time higher id fact",
            retain=0.90,
            updated_at="2026-04-09T10:00:00Z",
        ),
        accepted_workspace_record(
            "mem_20260408_11111111",
            kind="fact",
            summary="Older tied fact",
            retain=0.90,
            updated_at="2026-04-09T08:00:00Z",
        ),
    ):
        write_workspace_canon(config, record)

    [plan] = build_digest_plans(
        config,
        scope="workspace",
        generated_at="2026-04-09T12:00:00Z",
    )

    assert section_bullets(plan.content, "## Facts") == [
        "- Highest retain fact",
        "- Newer tied fact",
        "- Same time lower id fact",
        "- Same time higher id fact",
        "- Older tied fact",
    ]


def test_build_digest_plans_enforces_workspace_bullet_budget(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    for index in range(45):
        write_workspace_canon(
            config,
            accepted_workspace_record(
                f"mem_20260408_{index:08x}",
                kind="workflow",
                summary=f"Workspace bullet {index:02d}",
                retain=1.0 - (index * 0.01),
                updated_at="2026-04-09T10:00:00Z",
            ),
        )

    [plan] = build_digest_plans(
        config,
        scope="workspace",
        generated_at="2026-04-09T12:00:00Z",
    )

    assert plan.included_count == 40
    assert plan.omitted_count == 5
    assert len(plan.content.encode("utf-8")) <= 6000
    assert "- Workspace bullet 39" in plan.content
    assert "- Workspace bullet 40" not in plan.content


def test_build_digest_plans_enforces_global_byte_budget(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    for index in range(20):
        write_global_canon(
            config,
            accepted_global_record(
                f"mem_20260408_{index:08x}",
                kind="workflow",
                summary=long_summary(f"Global byte budget {index:02d}"),
                retain=1.0 - (index * 0.01),
                updated_at="2026-04-09T10:00:00Z",
            ),
        )

    [plan] = build_digest_plans(
        config,
        scope="global",
        generated_at="2026-04-09T12:00:00Z",
    )

    assert plan.scope == "global"
    assert plan.workspace_label == "-"
    assert plan.included_count < 20
    assert plan.omitted_count > 0
    assert len(plan.content.encode("utf-8")) <= 3000
    assert "- " + long_summary("Global byte budget 00") in plan.content
    assert "- " + long_summary("Global byte budget 19") not in plan.content


def test_compile_command_defaults_to_workspace_scope(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_11111111",
            summary="Workspace-only digest record",
        ),
    )
    write_global_canon(
        config,
        accepted_global_record(
            "mem_20260408_22222222",
            summary="Global digest record",
        ),
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-09T12:00:00Z")

    result = main(
        [
            "compile",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        f"compiled\tworkspace\tmem-wiz\t{config.workspace_cache / 'digest.md'}\t1\t0\n"
    )
    assert captured.err == ""
    assert (config.workspace_cache / "digest.md").exists()
    assert not (config.global_cache / "digest.md").exists()


def test_compile_command_scope_all_preflights_both_scopes_before_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_11111111",
            summary="Workspace compile record",
        ),
    )
    corrupt_global_path = config.global_canon / "mem_20260408_deadbeef.yaml"
    corrupt_global_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_global_path.write_text("summary: [broken\n", encoding="utf-8")

    result = main(
        [
            "compile",
            "--scope",
            "all",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert str(corrupt_global_path) in captured.err
    assert not (config.workspace_cache / "digest.md").exists()
    assert not (config.global_cache / "digest.md").exists()


def test_compile_command_prints_compiled_rows_and_writes_both_digests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_11111111",
            summary="Workspace compiled summary",
        ),
    )
    write_global_canon(
        config,
        accepted_global_record(
            "mem_20260408_22222222",
            summary="Global compiled summary",
        ),
    )
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-09T12:00:00Z")

    result = main(
        [
            "compile",
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
        f"compiled\tworkspace\tmem-wiz\t{config.workspace_cache / 'digest.md'}\t1\t0\n"
        f"compiled\tglobal\t-\t{config.global_cache / 'digest.md'}\t1\t0\n"
    )
    assert captured.err == ""
    assert (config.workspace_cache / "digest.md").read_text(encoding="utf-8")
    assert (config.global_cache / "digest.md").read_text(encoding="utf-8")


def test_compile_command_scope_all_restores_existing_digests_when_publish_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memwiz.fsops import atomic_replace as fs_atomic_replace

    config = make_config(tmp_path)
    workspace_digest = config.workspace_cache / "digest.md"
    global_digest = config.global_cache / "digest.md"
    write_workspace_canon(
        config,
        accepted_workspace_record(
            "mem_20260408_11111111",
            summary="Workspace compiled summary",
        ),
    )
    write_global_canon(
        config,
        accepted_global_record(
            "mem_20260408_22222222",
            summary="Global compiled summary",
        ),
    )
    workspace_digest.write_text("old workspace digest\n", encoding="utf-8")
    global_digest.write_text("old global digest\n", encoding="utf-8")

    replace_calls = 0

    def fail_second_replace(source: Path, destination: Path) -> None:
        nonlocal replace_calls

        replace_calls += 1
        if replace_calls == 2:
            raise OSError("simulated replace failure")

        fs_atomic_replace(source, destination)

    monkeypatch.setattr("memwiz.commands.compile.atomic_replace", fail_second_replace)
    monkeypatch.setenv("MEMWIZ_FIXED_NOW", "2026-04-09T12:00:00Z")

    result = main(
        [
            "compile",
            "--scope",
            "all",
            "--root",
            str(config.root),
            "--workspace",
            "mem-wiz",
        ]
    )
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "Compile failed: simulated replace failure\n"
    assert workspace_digest.read_text(encoding="utf-8") == "old workspace digest\n"
    assert global_digest.read_text(encoding="utf-8") == "old global digest\n"


def test_compile_command_returns_six_when_root_lock_is_unavailable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_config(tmp_path)
    config.root.mkdir(parents=True, exist_ok=True)
    lock_path = config.root / LOCK_FILENAME
    lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    result = main(
        [
            "compile",
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


def digest_headings(content: str) -> list[str]:
    return [line for line in content.splitlines() if line.startswith("## ")]


def section_bullets(content: str, heading: str) -> list[str]:
    lines = content.splitlines()
    start = lines.index(heading) + 1
    bullets: list[str] = []

    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.startswith("- "):
            bullets.append(line)

    return bullets


def long_summary(label: str) -> str:
    padding = "x" * (160 - len(label) - 1)
    return f"{label} {padding}"


def make_config(tmp_path: Path) -> MemwizConfig:
    return build_config(root=tmp_path / "mem-root", workspace="mem-wiz")


def accepted_workspace_record(
    record_id: str,
    *,
    summary: str = "Workspace compiled summary",
    kind: str = "workflow",
    retain: float = 0.90,
    updated_at: str = "2026-04-09T10:00:00Z",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="workspace",
        workspace="mem-wiz",
        kind=kind,
        summary=summary,
        details="Workspace digest details should never appear in compile output.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-09")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=0.75,
            scope_fit=1.0,
            retain=retain,
        ),
        status="accepted",
        tags=["compile"],
        decision=Decision(accepted_at="2026-04-09T07:00:00Z"),
        score_reasons=["durable", "reusable"],
        created_at="2026-04-09T07:00:00Z",
        updated_at=updated_at,
    )


def accepted_global_record(
    record_id: str,
    *,
    summary: str = "Global compiled summary",
    kind: str = "workflow",
    retain: float = 0.90,
    updated_at: str = "2026-04-09T10:00:00Z",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="global",
        kind=kind,
        summary=summary,
        details="Global digest details should never appear in compile output.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-09")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=0.75,
            scope_fit=1.0,
            retain=retain,
            promote=0.85,
        ),
        status="accepted",
        tags=["compile"],
        decision=Decision(accepted_at="2026-04-09T07:00:00Z"),
        score_reasons=["durable", "reusable"],
        provenance=Provenance(
            source_scope="workspace",
            source_workspace="mem-wiz",
            source_memory_id="mem_20260408_aaaaaaaa",
            promoted_at="2026-04-09T07:00:00Z",
            promotion_reason="Useful across future repositories.",
        ),
        created_at="2026-04-09T07:00:00Z",
        updated_at=updated_at,
    )
