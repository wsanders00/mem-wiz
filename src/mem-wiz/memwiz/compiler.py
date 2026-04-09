from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from memwiz.config import MemwizConfig
from memwiz.models import MemoryRecord
from memwiz.scoring import contains_secret_like_content
from memwiz.serde import load_record
from memwiz.storage import list_global_records, list_workspace_records


KIND_ORDER = (
    "preference",
    "constraint",
    "fact",
    "workflow",
    "decision",
    "warning",
)
SECTION_HEADINGS = {
    "preference": "## Preferences",
    "constraint": "## Constraints",
    "fact": "## Facts",
    "workflow": "## Workflows",
    "decision": "## Decisions",
    "warning": "## Warnings",
}
SCOPE_BUDGETS = {
    "workspace": (40, 6000),
    "global": (20, 3000),
}


class CompileValidationError(RuntimeError):
    path: Path
    reason: str

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


@dataclass(frozen=True)
class DigestPlan:
    scope: str
    workspace_label: str
    path: Path
    content: str
    included_count: int
    omitted_count: int


def build_digest_plans(
    config: MemwizConfig,
    *,
    scope: str,
    generated_at: str,
) -> list[DigestPlan]:
    normalized_scope = _validate_scope(scope)
    plans: list[DigestPlan] = []

    if normalized_scope in {"workspace", "all"}:
        plans.append(
            _build_scope_plan(
                config,
                scope="workspace",
                generated_at=generated_at,
            )
        )

    if normalized_scope in {"global", "all"}:
        plans.append(
            _build_scope_plan(
                config,
                scope="global",
                generated_at=generated_at,
            )
        )

    return plans


def _build_scope_plan(
    config: MemwizConfig,
    *,
    scope: str,
    generated_at: str,
) -> DigestPlan:
    if scope == "workspace":
        workspace_label = config.workspace_slug
        path = config.workspace_cache / "digest.md"
        scope_label = f"workspace:{config.workspace_slug}"
    else:
        workspace_label = "-"
        path = config.global_cache / "digest.md"
        scope_label = "global"

    records = _load_canon_records(config, scope)
    selected_records, omitted_count = _select_records(
        records,
        scope=scope,
        generated_at=generated_at,
        scope_label=scope_label,
    )
    content = _render_digest(
        generated_at=generated_at,
        scope_label=scope_label,
        records=selected_records,
        included_count=len(selected_records),
        omitted_count=omitted_count,
    )

    return DigestPlan(
        scope=scope,
        workspace_label=workspace_label,
        path=path,
        content=content,
        included_count=len(selected_records),
        omitted_count=omitted_count,
    )


def _validate_scope(scope: str) -> str:
    if scope not in {"workspace", "global", "all"}:
        raise ValueError(f"invalid compile scope: {scope}")

    return scope


def _load_canon_records(config: MemwizConfig, scope: str) -> list[MemoryRecord]:
    if scope == "workspace":
        paths = list_workspace_records(config, "canon")
        expected_scope = "workspace"
        expected_workspace = config.workspace_slug
    else:
        paths = list_global_records(config, "canon")
        expected_scope = "global"
        expected_workspace = None

    return [
        _load_canon_record(
            path,
            expected_scope=expected_scope,
            expected_workspace=expected_workspace,
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
        record_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CompileValidationError(path, f"failed to decode record: {exc}") from exc

    try:
        record = load_record(record_text)
    except yaml.YAMLError as exc:
        raise CompileValidationError(path, f"failed to decode YAML: {exc}") from exc
    except (AttributeError, TypeError, ValueError) as exc:
        raise CompileValidationError(path, f"record failed validation: {exc}") from exc

    if record.status != "accepted":
        raise CompileValidationError(
            path,
            f"canon record must be accepted, got {record.status}",
        )

    if record.scope != expected_scope:
        raise CompileValidationError(
            path,
            f"canon record scope must be {expected_scope}, got {record.scope}",
        )

    if expected_scope == "workspace" and record.workspace != expected_workspace:
        raise CompileValidationError(
            path,
            (
                "workspace canon record must belong to "
                f"{expected_workspace}, got {record.workspace}"
            ),
        )

    if contains_secret_like_content(*_secret_values(record)):
        raise CompileValidationError(
            path,
            "secret-like content detected in accepted canon",
        )

    return record


def _secret_values(record: MemoryRecord) -> tuple[str, ...]:
    return (
        record.summary,
        record.details or "",
        *(record.tags or []),
        *(item.ref for item in record.evidence),
        *(item.note for item in record.evidence if item.note),
    )


def _select_records(
    records: list[MemoryRecord],
    *,
    scope: str,
    generated_at: str,
    scope_label: str,
) -> tuple[list[MemoryRecord], int]:
    max_bullets, max_bytes = SCOPE_BUDGETS[scope]
    ranked_records = sorted(records, key=_record_sort_key)
    included_count = min(len(ranked_records), max_bullets)

    while True:
        selected_records = ranked_records[:included_count]
        omitted_count = len(ranked_records) - included_count
        content = _render_digest(
            generated_at=generated_at,
            scope_label=scope_label,
            records=selected_records,
            included_count=included_count,
            omitted_count=omitted_count,
        )

        if len(content.encode("utf-8")) <= max_bytes:
            return selected_records, omitted_count

        if included_count == 0:
            return [], len(ranked_records)

        included_count -= 1


def _render_digest(
    *,
    generated_at: str,
    scope_label: str,
    records: list[MemoryRecord],
    included_count: int,
    omitted_count: int,
) -> str:
    lines = [
        "# Mem-Wiz Digest",
        f"Generated: {generated_at}",
        f"Scope: {scope_label}",
        f"Included: {included_count}",
        f"Omitted: {omitted_count}",
        "",
    ]

    for kind in KIND_ORDER:
        kind_records = [record for record in records if record.kind == kind]
        if not kind_records:
            continue

        lines.append(SECTION_HEADINGS[kind])
        lines.extend(f"- {record.summary}" for record in kind_records)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _record_sort_key(record: MemoryRecord) -> tuple[float, float, str]:
    retain = record.score.retain if record.score is not None and record.score.retain is not None else 0.0
    return (
        -retain,
        -_timestamp_key(record.updated_at),
        record.id,
    )


def _timestamp_key(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
