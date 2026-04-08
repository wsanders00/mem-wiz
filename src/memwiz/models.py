from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping, Optional, Sequence

from memwiz.config import normalize_workspace_slug


SCHEMA_VERSION = 1
ALLOWED_SCOPES = {"workspace", "global"}
ALLOWED_STATUSES = {"captured", "accepted", "archived"}
ALLOWED_KINDS = {
    "preference",
    "constraint",
    "fact",
    "workflow",
    "decision",
    "warning",
}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_EVIDENCE_SOURCES = {
    "user",
    "conversation",
    "file",
    "command",
    "test",
    "issue",
    "doc",
    "agent",
}
ACCEPTED_SCORE_FIELDS = (
    "reuse",
    "specificity",
    "durability",
    "evidence",
    "novelty",
    "scope_fit",
    "retain",
)
ID_PATTERN = re.compile(r"^mem_\d{8}_[0-9a-f]{8}$")


@dataclass
class EvidenceItem:
    source: str
    ref: str
    note: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source not in ALLOWED_EVIDENCE_SOURCES:
            raise ValueError(f"source must be one of {sorted(ALLOWED_EVIDENCE_SOURCES)}")

        if not self.ref or not self.ref.strip():
            raise ValueError("ref is required")

        self.ref = self.ref.strip()

        if self.note is not None:
            self.note = self.note.strip() or None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceItem":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "ref": self.ref,
        }

        if self.note is not None:
            payload["note"] = self.note

        return payload


@dataclass
class Score:
    reuse: Optional[float] = None
    specificity: Optional[float] = None
    durability: Optional[float] = None
    evidence: Optional[float] = None
    novelty: Optional[float] = None
    scope_fit: Optional[float] = None
    retain: Optional[float] = None
    promote: Optional[float] = None

    def __post_init__(self) -> None:
        for field_name in (
            "reuse",
            "specificity",
            "durability",
            "evidence",
            "novelty",
            "scope_fit",
            "retain",
            "promote",
        ):
            value = getattr(self, field_name)

            if value is None:
                continue

            setattr(self, field_name, _coerce_score_value(field_name, value))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Score":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}

        for field_name in (
            "reuse",
            "specificity",
            "durability",
            "evidence",
            "novelty",
            "scope_fit",
            "retain",
            "promote",
        ):
            value = getattr(self, field_name)

            if value is not None:
                payload[field_name] = value

        return payload


@dataclass
class Decision:
    accepted_at: Optional[str] = None
    archived_at: Optional[str] = None
    archive_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.accepted_at is not None:
            self.accepted_at = normalize_timestamp(self.accepted_at)

        if self.archived_at is not None:
            self.archived_at = normalize_timestamp(self.archived_at)

        if self.archive_reason is not None:
            self.archive_reason = self.archive_reason.strip() or None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Decision":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}

        if self.accepted_at is not None:
            payload["accepted_at"] = self.accepted_at

        if self.archived_at is not None:
            payload["archived_at"] = self.archived_at

        if self.archive_reason is not None:
            payload["archive_reason"] = self.archive_reason

        return payload


@dataclass
class Provenance:
    source_scope: str
    source_workspace: str
    source_memory_id: str
    promoted_at: str
    promotion_reason: str

    def __post_init__(self) -> None:
        if self.source_scope != "workspace":
            raise ValueError("provenance.source_scope must be workspace")

        self.source_workspace = normalize_workspace_slug(self.source_workspace)
        self.source_memory_id = normalize_memory_id(self.source_memory_id)
        self.promoted_at = normalize_timestamp(self.promoted_at)

        if not self.promotion_reason or not self.promotion_reason.strip():
            raise ValueError("provenance.promotion_reason is required")

        self.promotion_reason = self.promotion_reason.strip()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Provenance":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_scope": self.source_scope,
            "source_workspace": self.source_workspace,
            "source_memory_id": self.source_memory_id,
            "promoted_at": self.promoted_at,
            "promotion_reason": self.promotion_reason,
        }


@dataclass
class MemoryRecord:
    id: str
    scope: str
    kind: str
    summary: str
    evidence: Sequence[EvidenceItem | Mapping[str, Any]]
    status: str
    created_at: str
    updated_at: str
    schema_version: int = SCHEMA_VERSION
    workspace: Optional[str] = None
    details: Optional[str] = None
    confidence: Optional[str] = None
    score: Optional[Score | Mapping[str, Any]] = None
    tags: Optional[Sequence[str]] = None
    decision: Optional[Decision | Mapping[str, Any]] = None
    score_reasons: Optional[Sequence[str]] = None
    supersedes: Optional[str] = None
    provenance: Optional[Provenance | Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        self.schema_version = int(self.schema_version)

        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("schema_version must equal 1")

        self.id = normalize_memory_id(self.id)
        _validate_choice("scope", self.scope, ALLOWED_SCOPES)
        _validate_choice("kind", self.kind, ALLOWED_KINDS)
        _validate_choice("status", self.status, ALLOWED_STATUSES)

        if self.scope == "workspace":
            if self.workspace is None:
                raise ValueError("workspace scope requires workspace")

            self.workspace = normalize_workspace_slug(self.workspace)
        elif self.workspace is not None:
            raise ValueError("global scope forbids workspace")

        self.summary = _normalize_summary(self.summary)
        self.details = _normalize_optional_text(self.details)
        self.evidence = [_coerce_evidence_item(item) for item in self.evidence]

        if not self.evidence:
            raise ValueError("evidence must contain at least one item")

        if self.confidence is not None:
            _validate_choice("confidence", self.confidence, ALLOWED_CONFIDENCE)

        self.score = _coerce_score(self.score)
        self.tags = normalize_tags(self.tags)
        self.decision = _coerce_decision(self.decision)
        self.score_reasons = _normalize_reasons(self.score_reasons)
        self.supersedes = (
            normalize_memory_id(self.supersedes)
            if self.supersedes is not None
            else None
        )
        self.provenance = _coerce_provenance(self.provenance)
        self.created_at = normalize_timestamp(self.created_at)
        self.updated_at = normalize_timestamp(self.updated_at)

        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")

        self._validate_status_rules()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryRecord":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "scope": self.scope,
            "kind": self.kind,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

        if self.workspace is not None:
            payload["workspace"] = self.workspace

        if self.details is not None:
            payload["details"] = self.details

        if self.confidence is not None:
            payload["confidence"] = self.confidence

        if self.score is not None:
            payload["score"] = self.score.to_dict()

        if self.tags:
            payload["tags"] = list(self.tags)

        if self.decision is not None:
            payload["decision"] = self.decision.to_dict()

        if self.score_reasons:
            payload["score_reasons"] = list(self.score_reasons)

        if self.supersedes is not None:
            payload["supersedes"] = self.supersedes

        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()

        return payload

    def _validate_status_rules(self) -> None:
        if self.score_reasons is not None and self.score is None:
            raise ValueError("score_reasons require score")

        if self.status == "captured":
            if self.scope != "workspace":
                raise ValueError("captured records require workspace scope")

            if self.decision is not None:
                raise ValueError("captured records cannot include decision")

            if self.provenance is not None:
                raise ValueError("captured records cannot include provenance")

            if self.score is not None and self.score.promote is not None:
                raise ValueError("score.promote is only valid for global records")

            return

        if self.score is None:
            raise ValueError(f"{self.status} records require score")

        _require_score_fields(self.score, ACCEPTED_SCORE_FIELDS)

        if not self.score_reasons:
            raise ValueError(f"{self.status} records require score_reasons")

        if self.decision is None or self.decision.accepted_at is None:
            raise ValueError(f"{self.status} records require decision.accepted_at")

        if self.status == "accepted":
            if self.decision.archived_at is not None or self.decision.archive_reason is not None:
                raise ValueError("accepted records cannot include archived decision fields")
        else:
            if self.decision.archived_at is None:
                raise ValueError("archived records require decision.archived_at")

            if self.decision.archive_reason is None:
                raise ValueError("archived records require decision.archive_reason")

        if self.scope == "global":
            if self.score.promote is None:
                raise ValueError("global records require score.promote")

            if self.provenance is None:
                raise ValueError("global records require provenance")
        else:
            if self.score.promote is not None:
                raise ValueError("score.promote is only valid for global records")

            if self.provenance is not None:
                raise ValueError("workspace records cannot include provenance")


def normalize_memory_id(value: str) -> str:
    candidate = value.strip().lower()

    if not ID_PATTERN.match(candidate):
        raise ValueError("id must match mem_YYYYMMDD_<8 lowercase hex>")

    return candidate


def normalize_timestamp(value: str) -> str:
    candidate = value.strip()

    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"

    try:
        moment = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("timestamp must be RFC 3339 with timezone") from exc

    if moment.tzinfo is None:
        raise ValueError("timestamp must be RFC 3339 with timezone")

    normalized = moment.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def normalize_tags(tags: Optional[Sequence[str]]) -> list[str]:
    if tags is None:
        return []

    normalized = {_normalize_tag(tag) for tag in tags}
    return sorted(normalized)


def _coerce_evidence_item(
    item: EvidenceItem | Mapping[str, Any],
) -> EvidenceItem:
    if isinstance(item, EvidenceItem):
        return item

    return EvidenceItem.from_dict(item)


def _coerce_score(score: Optional[Score | Mapping[str, Any]]) -> Optional[Score]:
    if score is None:
        return None

    if isinstance(score, Score):
        return score

    return Score.from_dict(score)


def _coerce_decision(
    decision: Optional[Decision | Mapping[str, Any]],
) -> Optional[Decision]:
    if decision is None:
        return None

    if isinstance(decision, Decision):
        return decision

    return Decision.from_dict(decision)


def _coerce_provenance(
    provenance: Optional[Provenance | Mapping[str, Any]],
) -> Optional[Provenance]:
    if provenance is None:
        return None

    if isinstance(provenance, Provenance):
        return provenance

    return Provenance.from_dict(provenance)


def _coerce_score_value(field_name: str, value: Any) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")

    numeric_value = float(value)

    if numeric_value < 0.0 or numeric_value > 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")

    return numeric_value


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


def _normalize_summary(summary: str) -> str:
    cleaned = summary.strip()

    if not cleaned:
        raise ValueError("summary is required")

    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError("summary must be single-line")

    if len(cleaned) > 160:
        raise ValueError("summary must be <= 160 characters")

    return cleaned


def _normalize_reasons(reasons: Optional[Sequence[str]]) -> Optional[list[str]]:
    if reasons is None:
        return None

    normalized = [reason.strip() for reason in reasons if reason.strip()]
    return normalized or None


def _normalize_tag(tag: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", tag.strip().lower())
    slug = slug.strip("-")

    if not slug:
        raise ValueError("tags must normalize to lowercase kebab-case")

    return slug


def _require_score_fields(score: Score, field_names: Iterable[str]) -> None:
    missing_fields = [
        field_name
        for field_name in field_names
        if getattr(score, field_name) is None
    ]

    if missing_fields:
        missing_text = ", ".join(f"score.{field_name}" for field_name in missing_fields)
        raise ValueError(f"missing required score fields: {missing_text}")


def _validate_choice(field_name: str, value: str, choices: set[str]) -> None:
    if value not in choices:
        raise ValueError(f"{field_name} must be one of {sorted(choices)}")
