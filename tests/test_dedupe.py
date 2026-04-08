from __future__ import annotations

from memwiz.dedupe import (
    is_near_duplicate,
    is_strong_duplicate,
    normalize_summary,
    resolve_supersedes,
    select_duplicate_winner,
    superseded_records,
)
from memwiz.models import Decision, EvidenceItem, MemoryRecord, Provenance, Score


def test_normalized_summary_strong_duplicate_detection() -> None:
    left = make_workspace_record(summary="Prefer explicit promotion from workspace to global!")
    right = make_workspace_record(summary="prefer explicit promotion from workspace to global")

    assert normalize_summary(left.summary) == "prefer explicit promotion from workspace to global"
    assert is_strong_duplicate(left, right)


def test_near_duplicate_detection_uses_token_overlap_threshold() -> None:
    left = make_workspace_record(summary="Prefer concise bug first review guidance")
    right = make_workspace_record(summary="Prefer concise bug first review guidance everywhere")

    assert is_near_duplicate(left, right)
    assert not is_strong_duplicate(left, right)


def test_winner_selection_uses_the_configured_tie_break_order() -> None:
    evidence_winner = select_duplicate_winner(
        [
            make_workspace_record(record_id="mem_20260408_aaa11111", evidence_score=0.75),
            make_workspace_record(record_id="mem_20260408_bbb22222", evidence_score=1.0),
        ]
    )
    durability_winner = select_duplicate_winner(
        [
            make_workspace_record(
                record_id="mem_20260408_ccc33333",
                evidence_score=1.0,
                durability_score=0.75,
            ),
            make_workspace_record(
                record_id="mem_20260408_ddd44444",
                evidence_score=1.0,
                durability_score=1.0,
            ),
        ]
    )
    retain_winner = select_duplicate_winner(
        [
            make_workspace_record(
                record_id="mem_20260408_eee55555",
                evidence_score=1.0,
                durability_score=1.0,
                retain_score=0.75,
            ),
            make_workspace_record(
                record_id="mem_20260408_fff66666",
                evidence_score=1.0,
                durability_score=1.0,
                retain_score=1.0,
            ),
        ]
    )
    timestamp_winner = select_duplicate_winner(
        [
            make_workspace_record(
                record_id="mem_20260408_1111aaaa",
                evidence_score=1.0,
                durability_score=1.0,
                retain_score=1.0,
                updated_at="2026-04-08T15:30:00Z",
            ),
            make_workspace_record(
                record_id="mem_20260408_2222bbbb",
                evidence_score=1.0,
                durability_score=1.0,
                retain_score=1.0,
                updated_at="2026-04-08T16:30:00Z",
            ),
        ]
    )
    id_winner = select_duplicate_winner(
        [
            make_workspace_record(
                record_id="mem_20260408_fff99999",
                evidence_score=1.0,
                durability_score=1.0,
                retain_score=1.0,
                updated_at="2026-04-08T16:30:00Z",
            ),
            make_workspace_record(
                record_id="mem_20260408_aaa00000",
                evidence_score=1.0,
                durability_score=1.0,
                retain_score=1.0,
                updated_at="2026-04-08T16:30:00Z",
            ),
        ]
    )

    assert evidence_winner.id == "mem_20260408_bbb22222"
    assert durability_winner.id == "mem_20260408_ddd44444"
    assert retain_winner.id == "mem_20260408_fff66666"
    assert timestamp_winner.id == "mem_20260408_2222bbbb"
    assert id_winner.id == "mem_20260408_aaa00000"


def test_supersedes_resolves_only_within_the_same_scope() -> None:
    old_workspace = make_workspace_record(record_id="mem_20260408_0dd11111")
    new_workspace = make_workspace_record(
        record_id="mem_20260408_0dd22222",
        supersedes="mem_20260408_0dd11111",
    )
    global_record = make_global_record(record_id="mem_20260408_0dd11111")

    assert resolve_supersedes(new_workspace, [old_workspace, global_record]) == old_workspace
    assert superseded_records([old_workspace, new_workspace, global_record]) == [old_workspace]


def test_global_provenance_duplicates_are_blocked_even_with_different_summaries() -> None:
    left = make_global_record(
        record_id="mem_20260408_aaa11111",
        summary="Promoted guidance for cross-repo review hygiene.",
        source_memory_id="mem_20260408_abc99999",
    )
    right = make_global_record(
        record_id="mem_20260408_bbb22222",
        summary="Promoted workflow for keeping review feedback concise.",
        source_memory_id="mem_20260408_abc99999",
    )

    assert is_strong_duplicate(left, right)


def make_workspace_record(
    *,
    record_id: str = "mem_20260408_abc123ef",
    summary: str = "Prefer concise contributor guidance.",
    evidence_score: float = 1.0,
    durability_score: float = 1.0,
    retain_score: float = 1.0,
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
        details="This remains useful after the current task.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=durability_score,
            evidence=evidence_score,
            novelty=1.0,
            scope_fit=1.0,
            retain=retain_score,
        ),
        status="accepted",
        tags=["dedupe"],
        decision=Decision(accepted_at="2026-04-08T15:30:00Z"),
        score_reasons=["durable", "evidence-backed"],
        supersedes=supersedes,
        provenance=None,
        created_at="2026-04-08T15:30:00Z",
        updated_at=updated_at,
    )


def make_global_record(
    *,
    record_id: str = "mem_20260408_def456ab",
    summary: str = "Promoted contributor guidance for future repositories.",
    source_memory_id: str = "mem_20260408_abc99999",
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=1,
        id=record_id,
        scope="global",
        workspace=None,
        kind="workflow",
        summary=summary,
        details="This remains useful across future repositories.",
        evidence=[EvidenceItem(source="conversation", ref="turn:user:2026-04-08")],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=1.0,
            scope_fit=1.0,
            retain=1.0,
            promote=0.82,
        ),
        status="accepted",
        tags=["dedupe"],
        decision=Decision(accepted_at="2026-04-08T15:30:00Z"),
        score_reasons=["durable", "evidence-backed"],
        supersedes=None,
        provenance=Provenance(
            source_scope="workspace",
            source_workspace="mem-wiz",
            source_memory_id=source_memory_id,
            promoted_at="2026-04-08T16:00:00Z",
            promotion_reason="Useful across future repositories.",
        ),
        created_at="2026-04-08T15:30:00Z",
        updated_at="2026-04-08T15:30:00Z",
    )
