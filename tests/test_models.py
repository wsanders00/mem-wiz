from __future__ import annotations

import pytest

from memwiz.models import (
    Decision,
    EvidenceItem,
    MemoryRecord,
    Provenance,
    Score,
)
from memwiz.serde import dump_record, load_record


def test_schema_version_is_locked_to_one() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        make_workspace_accepted_record(schema_version=2)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("scope", "team"),
        ("status", "promoted"),
        ("kind", "habit"),
        ("confidence", "certain"),
    ],
)
def test_allowed_enum_values_are_enforced(field_name: str, value: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        make_workspace_accepted_record(**{field_name: value})


def test_required_fields_are_enforced_by_status() -> None:
    with pytest.raises(ValueError, match="workspace scope"):
        make_workspace_accepted_record(status="captured", scope="global", workspace=None)

    with pytest.raises(ValueError, match="accepted_at"):
        make_workspace_accepted_record(status="accepted", decision=Decision())

    with pytest.raises(ValueError, match="archived_at"):
        make_workspace_accepted_record(
            status="archived",
            decision=Decision(accepted_at="2026-04-08T15:30:00Z"),
        )


def test_scored_captured_records_remain_valid_without_decision() -> None:
    record = make_workspace_accepted_record(
        status="captured",
        score=Score(
            reuse=1.0,
            specificity=0.75,
            durability=0.75,
            evidence=1.0,
            novelty=0.5,
            scope_fit=1.0,
            retain=0.82,
        ),
        score_reasons=["durable workspace convention"],
        decision=None,
    )

    assert record.status == "captured"
    assert record.decision is None
    assert record.score is not None


def test_global_records_require_workspace_provenance() -> None:
    with pytest.raises(ValueError, match="provenance"):
        make_global_accepted_record(provenance=None)


def test_global_accepted_records_require_promote_score() -> None:
    with pytest.raises(ValueError, match="score.promote"):
        make_global_accepted_record(score=make_workspace_accepted_record().score)


def test_summary_must_be_single_line_and_within_length_limit() -> None:
    with pytest.raises(ValueError, match="summary"):
        make_workspace_accepted_record(summary="line one\nline two")

    with pytest.raises(ValueError, match="summary"):
        make_workspace_accepted_record(summary="x" * 161)


def test_id_timestamp_and_tags_are_normalized() -> None:
    record = make_workspace_accepted_record(
        id="MEM_20260408_ABC123EF",
        created_at="2026-04-08T10:30:00-05:00",
        updated_at="2026-04-08T15:30:00+00:00",
        tags=["Team Notes", "memory-model", "team_notes"],
    )

    assert record.id == "mem_20260408_abc123ef"
    assert record.created_at == "2026-04-08T15:30:00Z"
    assert record.updated_at == "2026-04-08T15:30:00Z"
    assert record.tags == ["memory-model", "team-notes"]


def test_yaml_round_trip_preserves_record_structure() -> None:
    record = make_global_accepted_record()

    serialized = dump_record(record)
    loaded = load_record(serialized)

    assert loaded == record


def make_workspace_accepted_record(**overrides) -> MemoryRecord:
    data = {
        "schema_version": 1,
        "id": "mem_20260408_abc123ef",
        "scope": "workspace",
        "workspace": "mem-wiz",
        "kind": "preference",
        "summary": "Prefer explicit promotion from workspace to global.",
        "details": "Global memory should stay curated and conservative.",
        "evidence": [
            EvidenceItem(
                source="conversation",
                ref="turn:user:2026-04-08",
                note="User requested explicit promotion rules.",
            )
        ],
        "confidence": "high",
        "score": Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=0.75,
            scope_fit=1.0,
            retain=0.98,
        ),
        "status": "accepted",
        "tags": ["memory-model", "promotion"],
        "decision": Decision(accepted_at="2026-04-08T15:30:00Z"),
        "score_reasons": [
            "stable user preference",
            "likely reusable",
            "directly supported by conversation",
        ],
        "supersedes": None,
        "provenance": None,
        "created_at": "2026-04-08T15:30:00Z",
        "updated_at": "2026-04-08T15:30:00Z",
    }
    data.update(overrides)
    return MemoryRecord(**data)


def make_global_accepted_record(**overrides) -> MemoryRecord:
    data = {
        "scope": "global",
        "workspace": None,
        "score": Score(
            reuse=1.0,
            specificity=1.0,
            durability=1.0,
            evidence=1.0,
            novelty=0.75,
            scope_fit=1.0,
            retain=0.95,
            promote=0.83,
        ),
        "provenance": Provenance(
            source_scope="workspace",
            source_workspace="mem-wiz",
            source_memory_id="mem_20260408_abc123ef",
            promoted_at="2026-04-08T16:00:00Z",
            promotion_reason="High-evidence durable workflow.",
        ),
    }
    data.update(overrides)
    return make_workspace_accepted_record(**data)
