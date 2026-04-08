from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from memwiz.models import MemoryRecord
from memwiz.policy import (
    DISQUALIFIERS,
    FACTOR_VALUES,
    FACTOR_WEIGHTS,
    GLOBAL_PROMOTION_MIN_DURABILITY,
    GLOBAL_PROMOTION_MIN_EVIDENCE,
    PROMOTE_THRESHOLD,
)


SECRET_MARKERS = (
    "secret",
    "password",
    "api key",
    "token",
    "sk-",
    "access key",
)
FILLER_MARKERS = (
    "thanks",
    "sounds good",
    "okay",
    "got it",
    "noted",
    "will do",
)
STATUS_MARKERS = (
    "status update",
    "in progress",
    "working on",
    "completed",
    "done",
    "todo",
    "follow up",
)
TEMPORARY_MARKERS = (
    "temporary",
    "for now",
    "today only",
    "this week",
    "current sprint",
)
GUESS_MARKERS = (
    "maybe",
    "probably",
    "might",
    "guess",
    "perhaps",
)
STRONG_EVIDENCE_SOURCES = {
    "user",
    "conversation",
    "file",
    "command",
    "test",
    "issue",
    "doc",
}


@dataclass(frozen=True)
class FactorScores:
    reuse: float
    specificity: float
    durability: float
    evidence: float
    novelty: float
    scope_fit: float

    def __post_init__(self) -> None:
        for field_name in (
            "reuse",
            "specificity",
            "durability",
            "evidence",
            "novelty",
            "scope_fit",
        ):
            value = float(getattr(self, field_name))

            if value not in FACTOR_VALUES:
                raise ValueError("factor scores must use the five-point scale")

            object.__setattr__(self, field_name, value)


@dataclass(frozen=True)
class ScoreResult:
    factors: FactorScores
    total: float
    disqualifiers: tuple[str, ...] = ()


def calculate_retain_score(factors: FactorScores) -> float:
    return _aggregate_score(factors)


def calculate_promote_score(factors: FactorScores) -> float:
    return _aggregate_score(factors)


def evaluate_record(
    record: MemoryRecord,
    *,
    target_scope: str,
    has_strong_duplicate: bool = False,
    has_near_duplicate: bool = False,
) -> ScoreResult:
    factors = FactorScores(
        reuse=_score_reuse(record, target_scope=target_scope),
        specificity=_score_specificity(record),
        durability=_score_durability(record),
        evidence=_score_evidence(record),
        novelty=_score_novelty(
            has_strong_duplicate=has_strong_duplicate,
            has_near_duplicate=has_near_duplicate,
        ),
        scope_fit=_score_scope_fit(record, target_scope=target_scope),
    )
    disqualifiers = _collect_disqualifiers(
        record,
        factors=factors,
        has_strong_duplicate=has_strong_duplicate,
    )

    if disqualifiers:
        return ScoreResult(
            factors=factors,
            total=0.0,
            disqualifiers=tuple(disqualifiers),
        )

    if target_scope == "global" and record.scope == "workspace":
        total = calculate_promote_score(factors)
    else:
        total = calculate_retain_score(factors)

    return ScoreResult(
        factors=factors,
        total=total,
        disqualifiers=(),
    )


def is_promotion_eligible(result: ScoreResult) -> bool:
    return (
        not result.disqualifiers
        and result.total >= PROMOTE_THRESHOLD
        and result.factors.durability >= GLOBAL_PROMOTION_MIN_DURABILITY
        and result.factors.evidence >= GLOBAL_PROMOTION_MIN_EVIDENCE
    )


def _aggregate_score(factors: FactorScores) -> float:
    return round(
        FACTOR_WEIGHTS["reuse"] * factors.reuse
        + FACTOR_WEIGHTS["specificity"] * factors.specificity
        + FACTOR_WEIGHTS["durability"] * factors.durability
        + FACTOR_WEIGHTS["evidence"] * factors.evidence
        + FACTOR_WEIGHTS["novelty"] * factors.novelty
        + FACTOR_WEIGHTS["scope_fit"] * factors.scope_fit,
        2,
    )


def _score_reuse(record: MemoryRecord, *, target_scope: str) -> float:
    text = _record_text(record)

    if _contains_any(text, STATUS_MARKERS):
        return 0.0

    if target_scope == "global":
        if _mentions_workspace_context(record, text):
            return 0.0

        if record.kind in {"preference", "workflow", "constraint"}:
            return 1.0

        if record.kind in {"fact", "decision", "warning"}:
            return 0.75

        return 0.5

    if record.kind in {"preference", "workflow", "constraint"}:
        return 0.75

    if record.kind in {"fact", "decision", "warning"}:
        return 0.5

    return 0.25


def _score_specificity(record: MemoryRecord) -> float:
    normalized_summary = _normalize_text(record.summary)
    word_count = len(_summary_tokens(normalized_summary))

    if word_count < 4 or normalized_summary.startswith("remember this"):
        return 0.0

    if word_count >= 8 or record.details:
        return 1.0

    if word_count >= 6:
        return 0.75

    if word_count >= 4:
        return 0.5

    return 0.25


def _score_durability(record: MemoryRecord) -> float:
    text = _record_text(record)

    if _contains_any(text, TEMPORARY_MARKERS):
        return 0.0

    if record.kind in {"preference", "constraint", "workflow"}:
        return 1.0

    if record.kind in {"fact", "decision", "warning"}:
        return 0.75

    return 0.5


def _score_evidence(record: MemoryRecord) -> float:
    text = _record_text(record)
    sources = {item.source for item in record.evidence}

    if _contains_any(text, GUESS_MARKERS) and not sources.intersection(STRONG_EVIDENCE_SOURCES):
        return 0.0

    if sources.intersection(STRONG_EVIDENCE_SOURCES):
        return 1.0

    if len(record.evidence) > 1:
        return 0.75

    if sources == {"agent"}:
        return 0.25

    return 0.5


def _score_novelty(
    *,
    has_strong_duplicate: bool,
    has_near_duplicate: bool,
) -> float:
    if has_strong_duplicate:
        return 0.0

    if has_near_duplicate:
        return 0.25

    return 1.0


def _score_scope_fit(record: MemoryRecord, *, target_scope: str) -> float:
    if target_scope == record.scope:
        return 1.0

    if target_scope == "global":
        if _mentions_workspace_context(record, _record_text(record)):
            return 0.0

        if record.kind in {"preference", "workflow", "constraint"}:
            return 0.75

        return 0.5

    return 0.5


def _collect_disqualifiers(
    record: MemoryRecord,
    *,
    factors: FactorScores,
    has_strong_duplicate: bool,
) -> list[str]:
    text = _record_text(record)
    disqualifiers: list[str] = []

    if _contains_any(text, SECRET_MARKERS):
        disqualifiers.append(DISQUALIFIERS["secret_like"])

    if _contains_any(text, FILLER_MARKERS):
        disqualifiers.append(DISQUALIFIERS["filler"])

    if _contains_any(text, STATUS_MARKERS):
        disqualifiers.append(DISQUALIFIERS["status"])

    if factors.specificity == 0.0:
        disqualifiers.append(DISQUALIFIERS["vague"])

    if factors.evidence == 0.0:
        disqualifiers.append(DISQUALIFIERS["unsupported_guess"])

    if has_strong_duplicate:
        disqualifiers.append(DISQUALIFIERS["strong_duplicate"])

    return disqualifiers


def _record_text(record: MemoryRecord) -> str:
    parts = [record.summary]

    if record.details:
        parts.append(record.details)

    if record.tags:
        parts.extend(record.tags)

    return _normalize_text(" ".join(parts))


def _mentions_workspace_context(record: MemoryRecord, text: str) -> bool:
    workspace_markers = {
        "workspace-only",
        "this repo",
        "this repository",
        "in this repo",
        "in this repository",
    }

    if record.workspace:
        workspace_markers.add(record.workspace)

    return _contains_any(text, workspace_markers)


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _summary_tokens(summary: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", summary)
