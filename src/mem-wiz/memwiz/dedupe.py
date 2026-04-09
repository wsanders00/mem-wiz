from __future__ import annotations

from datetime import datetime
import re
from typing import Iterable, Optional, Sequence

from memwiz.models import MemoryRecord


def normalize_summary(summary: str) -> str:
    lowered = summary.lower()
    no_punctuation = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", no_punctuation).strip()


def is_strong_duplicate(left: MemoryRecord, right: MemoryRecord) -> bool:
    if left.scope == "global" and right.scope == "global":
        if _same_global_provenance(left, right):
            return True

    return (
        left.scope_key == right.scope_key
        and left.kind == right.kind
        and normalize_summary(left.summary) == normalize_summary(right.summary)
    )


def is_near_duplicate(left: MemoryRecord, right: MemoryRecord) -> bool:
    if left.scope_key != right.scope_key or left.kind != right.kind:
        return False

    if is_strong_duplicate(left, right):
        return False

    left_tokens = _summary_tokens(left.summary)
    right_tokens = _summary_tokens(right.summary)

    if not left_tokens or not right_tokens:
        return False

    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return overlap / union >= 0.85


def select_duplicate_winner(records: Sequence[MemoryRecord]) -> MemoryRecord:
    if not records:
        raise ValueError("at least one record is required")

    return sorted(records, key=_winner_key)[0]


def resolve_supersedes(
    record: MemoryRecord,
    candidates: Iterable[MemoryRecord],
) -> Optional[MemoryRecord]:
    if record.supersedes is None:
        return None

    for candidate in candidates:
        if candidate.id == record.id:
            continue

        if candidate.id == record.supersedes and candidate.scope_key == record.scope_key:
            return candidate

    return None


def superseded_records(records: Sequence[MemoryRecord]) -> list[MemoryRecord]:
    superseded_keys = {
        (resolved.id, resolved.scope_key)
        for record in records
        if record.status == "accepted"
        for resolved in [resolve_supersedes(record, records)]
        if resolved is not None
    }

    return [
        record
        for record in records
        if (record.id, record.scope_key) in superseded_keys
    ]


def _same_global_provenance(left: MemoryRecord, right: MemoryRecord) -> bool:
    if left.provenance is None or right.provenance is None:
        return False

    return (
        left.provenance.source_memory_id == right.provenance.source_memory_id
    )


def _summary_tokens(summary: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normalize_summary(summary)))


def _winner_key(record: MemoryRecord) -> tuple[float, float, float, float, str]:
    return (
        -_score_value(record, "evidence"),
        -_score_value(record, "durability"),
        -_score_value(record, "retain"),
        -_timestamp_key(record.updated_at),
        record.id,
    )


def _score_value(record: MemoryRecord, field_name: str) -> float:
    if record.score is None:
        return 0.0

    value = getattr(record.score, field_name)
    return 0.0 if value is None else float(value)


def _timestamp_key(value: str) -> float:
    timestamp = value.replace("Z", "+00:00")
    return datetime.fromisoformat(timestamp).timestamp()
