from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from memwiz.config import MemwizConfig
from memwiz.models import MemoryRecord, normalize_memory_id
from memwiz.serde import read_record
from memwiz.storage import list_global_records, list_workspace_records


class InvalidSearchQueryError(ValueError):
    pass


class InvalidMemoryIdError(ValueError):
    pass


class MemoryNotFoundError(LookupError):
    pass


class AmbiguousMemoryIdError(LookupError):
    pass


class CanonDecodeError(RuntimeError):
    path: Path
    reason: str

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


class CanonValidationError(RuntimeError):
    path: Path
    reason: str

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


@dataclass(frozen=True)
class SearchHit:
    record: MemoryRecord
    scope: str
    workspace_label: str
    rank_bucket: int


@dataclass(frozen=True)
class _ScopedRecord:
    record: MemoryRecord
    scope: str
    workspace_label: str


def search_records(
    config: MemwizConfig,
    query: str,
    *,
    scope: str,
    limit: int,
) -> list[SearchHit]:
    normalized_scope = _validate_scope(scope)
    normalized_limit = _validate_limit(limit)
    normalized_query, query_tokens = _normalize_query(query)

    hits = [
        SearchHit(
            record=scoped_record.record,
            scope=scoped_record.scope,
            workspace_label=scoped_record.workspace_label,
            rank_bucket=_rank_bucket(
                scoped_record.record,
                normalized_query,
                query_tokens,
            ),
        )
        for scoped_record in _load_scoped_records(config, normalized_scope)
        if _matches_query(scoped_record.record, query_tokens)
    ]

    return sorted(hits, key=_search_sort_key)[:normalized_limit]


def get_record(
    config: MemwizConfig,
    record_id: str,
    *,
    scope: str,
) -> MemoryRecord:
    normalized_scope = _validate_scope(scope)

    try:
        normalized_id = normalize_memory_id(record_id)
    except ValueError as exc:
        raise InvalidMemoryIdError(f"invalid memory id: {record_id}") from exc

    matches = [
        scoped_record.record
        for scoped_record in _load_scoped_records(config, normalized_scope)
        if scoped_record.record.id == normalized_id
    ]

    if not matches:
        raise MemoryNotFoundError(f"accepted memory not found: {normalized_id}")

    if len(matches) > 1:
        raise AmbiguousMemoryIdError(
            f"memory id {normalized_id} exists in both workspace and global; "
            "retry with --scope workspace or --scope global"
        )

    return matches[0]


def _validate_scope(scope: str) -> str:
    if scope not in {"workspace", "global", "all"}:
        raise ValueError(f"invalid retrieval scope: {scope}")

    return scope


def _validate_limit(limit: int) -> int:
    if limit <= 0:
        raise ValueError("limit must be a positive integer")

    return limit


def _normalize_query(query: str) -> tuple[str, list[str]]:
    normalized_query = query.strip().lower()
    query_tokens = normalized_query.split()

    if not query_tokens:
        raise InvalidSearchQueryError("search query cannot be empty")

    return normalized_query, query_tokens


def _load_scoped_records(config: MemwizConfig, scope: str) -> list[_ScopedRecord]:
    scoped_records: list[_ScopedRecord] = []

    if scope in {"workspace", "all"}:
        scoped_records.extend(
            _load_records_for_paths(
                list_workspace_records(config, "canon"),
                expected_scope="workspace",
                workspace_label=config.workspace_slug,
                expected_workspace=config.workspace_slug,
            )
        )

    if scope in {"global", "all"}:
        scoped_records.extend(
            _load_records_for_paths(
                list_global_records(config, "canon"),
                expected_scope="global",
                workspace_label="-",
                expected_workspace=None,
            )
        )

    return scoped_records


def _load_records_for_paths(
    paths: list[Path],
    *,
    expected_scope: str,
    workspace_label: str,
    expected_workspace: str | None,
) -> list[_ScopedRecord]:
    return [
        _ScopedRecord(
            record=_load_canon_record(
                path,
                expected_scope=expected_scope,
                expected_workspace=expected_workspace,
            ),
            scope=expected_scope,
            workspace_label=workspace_label,
        )
        for path in paths
    ]


def _load_canon_record(
    path: Path,
    *,
    expected_scope: str,
    expected_workspace: str | None,
) -> MemoryRecord:
    try:
        record = read_record(path)
    except yaml.YAMLError as exc:
        raise CanonDecodeError(path, str(exc)) from exc
    except ValueError as exc:
        raise CanonValidationError(path, str(exc)) from exc

    if record.status != "accepted":
        raise CanonValidationError(path, f"canon record must be accepted, got {record.status}")

    if record.scope != expected_scope:
        raise CanonValidationError(
            path,
            f"canon record scope must be {expected_scope}, got {record.scope}",
        )

    if expected_scope == "workspace" and record.workspace != expected_workspace:
        raise CanonValidationError(
            path,
            (
                "workspace canon record must belong to "
                f"{expected_workspace}, got {record.workspace}"
            ),
        )

    return record


def _matches_query(record: MemoryRecord, query_tokens: list[str]) -> bool:
    searchable_text = _searchable_text(record)
    return all(token in searchable_text for token in query_tokens)


def _searchable_text(record: MemoryRecord) -> str:
    text_parts = [
        record.id,
        record.scope,
        record.workspace or "",
        record.kind,
        record.summary,
        record.details or "",
        " ".join(record.tags or []),
        " ".join(item.ref for item in record.evidence),
        " ".join(item.note or "" for item in record.evidence),
    ]

    if record.provenance is not None:
        text_parts.extend(
            [
                record.provenance.source_workspace,
                record.provenance.source_memory_id,
            ]
        )

    return " ".join(text_parts).lower()


def _rank_bucket(
    record: MemoryRecord,
    normalized_query: str,
    query_tokens: list[str],
) -> int:
    record_id = record.id.lower()
    summary = record.summary.lower()
    kind = record.kind.lower()
    tags_text = " ".join(record.tags or []).lower()

    if record_id == normalized_query:
        return 1

    if record_id.startswith(normalized_query):
        return 2

    if normalized_query in summary:
        return 3

    if all(token in summary for token in query_tokens):
        return 4

    summary_kind_tags = " ".join(part for part in (summary, kind, tags_text) if part)
    if all(token in summary_kind_tags for token in query_tokens) and any(
        token in kind or token in tags_text for token in query_tokens
    ):
        return 5

    return 6


def _search_sort_key(hit: SearchHit) -> tuple[int, int, float, str]:
    return (
        hit.rank_bucket,
        0 if hit.scope == "workspace" else 1,
        -_timestamp_key(hit.record.updated_at),
        hit.record.id,
    )


def _timestamp_key(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
