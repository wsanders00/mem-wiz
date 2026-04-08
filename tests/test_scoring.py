from __future__ import annotations

import pytest

from memwiz.models import Decision, EvidenceItem, MemoryRecord, Score
from memwiz.policy import (
    DIGEST_BUDGETS,
    FACTOR_VALUES,
    FACTOR_WEIGHTS,
    GLOBAL_PROMOTION_MIN_DURABILITY,
    GLOBAL_PROMOTION_MIN_EVIDENCE,
    PROMOTE_THRESHOLD,
    RETAIN_THRESHOLD,
)
from memwiz.scoring import (
    FactorScores,
    ScoreResult,
    calculate_promote_score,
    calculate_retain_score,
    evaluate_record,
    is_promotion_eligible,
)


def test_policy_constants_match_the_design() -> None:
    assert FACTOR_WEIGHTS == {
        "reuse": 0.25,
        "durability": 0.20,
        "evidence": 0.20,
        "specificity": 0.15,
        "novelty": 0.10,
        "scope_fit": 0.10,
    }
    assert FACTOR_VALUES == {0.0, 0.25, 0.5, 0.75, 1.0}
    assert RETAIN_THRESHOLD == 0.55
    assert PROMOTE_THRESHOLD == 0.78
    assert GLOBAL_PROMOTION_MIN_DURABILITY == 0.70
    assert GLOBAL_PROMOTION_MIN_EVIDENCE == 0.80
    assert DIGEST_BUDGETS == {
        "global": {"bullets": 20, "bytes": 3000},
        "workspace": {"bullets": 40, "bytes": 6000},
    }


def test_factor_values_are_restricted_to_the_five_point_scale() -> None:
    with pytest.raises(ValueError, match="five-point scale"):
        FactorScores(
            reuse=0.6,
            specificity=0.75,
            durability=0.75,
            evidence=1.0,
            novelty=1.0,
            scope_fit=1.0,
        )


def test_rubric_bucket_examples_cover_each_factor() -> None:
    assert evaluate_record(
        make_workspace_record(summary="Status update: finished the migration."),
        target_scope="workspace",
    ).factors.reuse == 0.0

    assert evaluate_record(
        make_workspace_record(summary="Remember this."),
        target_scope="workspace",
    ).factors.specificity == 0.0

    assert evaluate_record(
        make_workspace_record(
            summary="Temporary deploy note for today only.",
            details="This is temporary and only for today.",
        ),
        target_scope="workspace",
    ).factors.durability == 0.0

    assert evaluate_record(
        make_workspace_record(
            summary="Maybe the user prefers tabs here.",
            evidence_sources=["agent"],
        ),
        target_scope="workspace",
    ).factors.evidence == 0.0

    assert evaluate_record(
        make_workspace_record(summary="Keep review notes concise."),
        target_scope="workspace",
        has_strong_duplicate=True,
    ).factors.novelty == 0.0

    assert evaluate_record(
        make_workspace_record(summary="Workspace-only review flow for this repo."),
        target_scope="global",
    ).factors.scope_fit == 0.0


def test_retain_score_is_deterministic_for_workspace_and_global_active_scope() -> None:
    workspace_result = evaluate_record(
        make_workspace_record(
            summary="Review pull requests with concise, bug-first findings.",
            details="Use the review checklist before suggesting optional refactors.",
        ),
        target_scope="workspace",
    )
    global_result = evaluate_record(
        make_global_record(
            summary="Prefer concise contributor guidance with explicit command examples.",
            details="This preference applies across future repositories.",
        ),
        target_scope="global",
    )

    assert workspace_result.total == 0.94
    assert global_result.total == 1.0


def test_promote_score_is_deterministic_for_global_admission() -> None:
    result = evaluate_record(
        make_workspace_record(
            summary="Prefer concise bug-first review findings across future repos.",
            details="This workflow remains useful across future repositories.",
        ),
        target_scope="global",
    )

    assert result.total == 0.98


def test_durable_high_evidence_memory_passes_retention() -> None:
    result = evaluate_record(
        make_workspace_record(
            summary="Capture durable workflow constraints before editing canon memory.",
            details="This workflow prevents accidental canon drift.",
        ),
        target_scope="workspace",
    )

    assert result.total >= RETAIN_THRESHOLD
    assert result.disqualifiers == ()


def test_promotion_eligibility_gates_are_enforced() -> None:
    strong_result = evaluate_record(
        make_workspace_record(
            summary="Prefer explicit global promotion for durable workflow preferences.",
            details="This practice stays useful across future repositories.",
        ),
        target_scope="global",
    )

    assert is_promotion_eligible(strong_result)
    assert not is_promotion_eligible(
        make_score_result(durability=0.5, evidence=1.0, total=0.90)
    )
    assert not is_promotion_eligible(
        make_score_result(durability=1.0, evidence=0.75, total=0.90)
    )
    assert not is_promotion_eligible(
        make_score_result(
            durability=1.0,
            evidence=1.0,
            total=0.90,
            disqualifiers=("strong duplicates in the target scope",),
        )
    )


def test_global_retain_score_is_distinct_from_workspace_admission_promote_score() -> None:
    global_retain = evaluate_record(
        make_global_record(
            summary="Prefer concise contributor guidance with explicit command examples.",
            details="This preference applies across future repositories.",
        ),
        target_scope="global",
    )
    promote_result = evaluate_record(
        make_workspace_record(
            summary="Prefer concise contributor guidance across future repositories.",
            details="This workflow stays useful after the current project.",
        ),
        target_scope="global",
    )

    assert global_retain.total == 1.0
    assert promote_result.total == 0.98
    assert global_retain.total != promote_result.total


@pytest.mark.parametrize(
    (
        "summary",
        "details",
        "evidence_sources",
        "has_strong_duplicate",
        "expected_disqualifier",
    ),
    [
        (
            "Store the secret token for later use.",
            "secret token value goes here",
            None,
            False,
            "secret-like content",
        ),
        (
            "Thanks, sounds good.",
            "This workflow remains useful after the current task.",
            None,
            False,
            "transient conversational filler",
        ),
        (
            "Maybe the user prefers tabs here.",
            "This workflow remains useful after the current task.",
            ["agent"],
            False,
            "unsupported guesses with no acceptable evidence",
        ),
        (
            "Keep review notes concise.",
            "This workflow remains useful after the current task.",
            None,
            True,
            "strong duplicates in the target scope",
        ),
    ],
)
def test_hard_disqualifiers_zero_the_score(
    summary: str,
    details: str,
    evidence_sources: list[str] | None,
    has_strong_duplicate: bool,
    expected_disqualifier: str,
) -> None:
    record = make_workspace_record(
        summary=summary,
        details=details,
        evidence_sources=evidence_sources,
    )

    result = evaluate_record(
        record,
        target_scope="workspace",
        has_strong_duplicate=has_strong_duplicate,
    )

    assert result.total == 0.0
    assert expected_disqualifier in result.disqualifiers


def make_workspace_record(
    *,
    summary: str,
    details: str = "This workflow remains useful after the current task.",
    evidence_sources: list[str] | None = None,
) -> MemoryRecord:
    sources = evidence_sources if evidence_sources is not None else ["conversation"]

    return MemoryRecord(
        schema_version=1,
        id="mem_20260408_abc123ef",
        scope="workspace",
        workspace="mem-wiz",
        kind="workflow",
        summary=summary,
        details=details,
        evidence=[EvidenceItem(source=source, ref=f"{source}:evidence") for source in sources],
        confidence="high",
        score=Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=1.0,
            scope_fit=1.0,
            retain=1.0,
        ),
        status="accepted",
        tags=["scoring"],
        decision=Decision(accepted_at="2026-04-08T15:30:00Z"),
        score_reasons=["durable", "evidence-backed"],
        supersedes=None,
        provenance=None,
        created_at="2026-04-08T15:30:00Z",
        updated_at="2026-04-08T15:30:00Z",
    )


def make_global_record(
    *,
    summary: str,
    details: str,
) -> MemoryRecord:
    record = make_workspace_record(summary=summary, details=details)
    payload = record.to_dict()
    payload["scope"] = "global"
    payload["workspace"] = None
    payload["score"]["promote"] = 0.82
    payload["provenance"] = {
        "source_scope": "workspace",
        "source_workspace": "mem-wiz",
        "source_memory_id": "mem_20260408_abc123ef",
        "promoted_at": "2026-04-08T16:00:00Z",
        "promotion_reason": "Still useful across future repositories.",
    }
    return MemoryRecord.from_dict(payload)


def make_score_result(
    *,
    durability: float,
    evidence: float,
    total: float,
    disqualifiers: tuple[str, ...] = (),
) -> ScoreResult:
    return ScoreResult(
        factors=FactorScores(
            reuse=1.0,
            specificity=1.0,
            durability=durability,
            evidence=evidence,
            novelty=1.0,
            scope_fit=0.75,
        ),
        total=total,
        disqualifiers=disqualifiers,
    )
