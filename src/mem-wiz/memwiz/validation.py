from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from memwiz.config import MemwizConfig
from memwiz.dedupe import is_strong_duplicate, resolve_supersedes, select_duplicate_winner
from memwiz.models import MemoryRecord
from memwiz.scoring import contains_secret_like_content
from memwiz.serde import load_record


@dataclass(frozen=True)
class LintFinding:
    level: str
    code: str
    subject: str
    message: str


@dataclass(frozen=True)
class _TreeSpec:
    path: Path
    scope: str
    expected_workspace: str | None
    expected_status: str
    state: str
    area_label: str
    category: str


@dataclass(frozen=True)
class _ScopedRecord:
    path: Path
    record: MemoryRecord
    state: str


def run_lint(config: MemwizConfig, *, scope: str) -> list[LintFinding]:
    normalized_scope = _validate_scope(scope)
    workspace_tree_findings: list[LintFinding] = []
    global_tree_findings: list[LintFinding] = []
    workspace_relation_findings: list[LintFinding] = []
    global_relation_findings: list[LintFinding] = []
    workspace_records: list[_ScopedRecord] = []
    global_records: list[_ScopedRecord] = []

    for tree in _selected_trees(config, normalized_scope):
        findings, records = _inspect_tree(tree)

        if tree.category == "workspace":
            workspace_tree_findings.extend(findings)
            workspace_records.extend(records)
        else:
            global_tree_findings.extend(findings)
            global_records.extend(records)

    workspace_relation_findings.extend(_duplicate_findings(workspace_records, scope_label="workspace"))
    workspace_relation_findings.extend(_supersedes_findings(workspace_records, scope_label="workspace"))
    global_relation_findings.extend(_duplicate_findings(global_records, scope_label="global"))
    global_relation_findings.extend(_supersedes_findings(global_records, scope_label="global"))

    findings: list[LintFinding] = []
    findings.extend(_sort_findings(workspace_tree_findings))
    findings.extend(_sort_findings(global_tree_findings))
    findings.extend(_sort_findings(workspace_relation_findings))
    findings.extend(_sort_findings(global_relation_findings))
    return findings


def _validate_scope(scope: str) -> str:
    if scope not in {"workspace", "global", "all"}:
        raise ValueError(f"invalid lint scope: {scope}")

    return scope


def _selected_trees(config: MemwizConfig, scope: str) -> list[_TreeSpec]:
    trees: list[_TreeSpec] = []

    if scope in {"workspace", "all"}:
        trees.extend(
            [
                _TreeSpec(
                    path=config.workspace_inbox,
                    scope="workspace",
                    expected_workspace=config.workspace_slug,
                    expected_status="captured",
                    state="inbox",
                    area_label="workspace inbox",
                    category="workspace",
                ),
                _TreeSpec(
                    path=config.workspace_canon,
                    scope="workspace",
                    expected_workspace=config.workspace_slug,
                    expected_status="accepted",
                    state="canon",
                    area_label="workspace canon",
                    category="workspace",
                ),
                _TreeSpec(
                    path=config.workspace_archive,
                    scope="workspace",
                    expected_workspace=config.workspace_slug,
                    expected_status="archived",
                    state="archive",
                    area_label="workspace archive",
                    category="workspace",
                ),
            ]
        )

    if scope in {"global", "all"}:
        trees.extend(
            [
                _TreeSpec(
                    path=config.global_canon,
                    scope="global",
                    expected_workspace=None,
                    expected_status="accepted",
                    state="canon",
                    area_label="global canon",
                    category="global",
                ),
                _TreeSpec(
                    path=config.global_archive,
                    scope="global",
                    expected_workspace=None,
                    expected_status="archived",
                    state="archive",
                    area_label="global archive",
                    category="global",
                ),
            ]
        )

    return trees


def _inspect_tree(tree: _TreeSpec) -> tuple[list[LintFinding], list[_ScopedRecord]]:
    if not tree.path.exists() or not tree.path.is_dir():
        return [], []

    findings: list[LintFinding] = []
    records: list[_ScopedRecord] = []

    for path in sorted(tree.path.glob("*.yaml"), key=lambda item: str(item)):
        try:
            record_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(
                LintFinding(
                    level="error",
                    code="record-decode",
                    subject=str(path),
                    message=f"failed to decode record: {exc}",
                )
            )
            continue

        try:
            record = load_record(record_text)
        except yaml.YAMLError as exc:
            findings.append(
                LintFinding(
                    level="error",
                    code="record-decode",
                    subject=str(path),
                    message=f"failed to decode YAML: {exc}",
                )
            )
            continue
        except (AttributeError, TypeError, ValueError) as exc:
            findings.append(
                LintFinding(
                    level="error",
                    code="record-invalid",
                    subject=str(path),
                    message=f"record failed validation: {exc}",
                )
            )
            continue

        state_is_valid = True

        if path.stem != record.id:
            findings.append(
                LintFinding(
                    level="error",
                    code="record-path-mismatch",
                    subject=str(path),
                    message=f"filename stem must match record id {record.id}",
                )
            )

        if record.status != tree.expected_status:
            findings.append(
                LintFinding(
                    level="error",
                    code="record-invalid",
                    subject=str(path),
                    message=(
                        f"{tree.area_label} record must be "
                        f"{tree.expected_status}, got {record.status}"
                    ),
                )
            )
            state_is_valid = False

        if record.scope != tree.scope:
            findings.append(
                LintFinding(
                    level="error",
                    code="record-invalid",
                    subject=str(path),
                    message=(
                        f"{tree.area_label} record scope must be "
                        f"{tree.scope}, got {record.scope}"
                    ),
                )
            )
            state_is_valid = False

        if record.workspace != tree.expected_workspace:
            findings.append(
                LintFinding(
                    level="error",
                    code="record-invalid",
                    subject=str(path),
                    message=(
                        f"{tree.area_label} record workspace must be "
                        f"{tree.expected_workspace}, got {record.workspace}"
                    ),
                )
            )
            state_is_valid = False

        if contains_secret_like_content(*_secret_values(record)):
            findings.append(
                LintFinding(
                    level="error",
                    code="secret-like-content",
                    subject=str(path),
                    message="secret-like content detected in managed memory",
                )
            )

        if state_is_valid:
            records.append(
                _ScopedRecord(
                    path=path,
                    record=record,
                    state=tree.state,
                )
            )

    return findings, records


def _duplicate_findings(
    records: list[_ScopedRecord],
    *,
    scope_label: str,
) -> list[LintFinding]:
    remaining = [record for record in records if record.state == "canon"]
    findings: list[LintFinding] = []

    while remaining:
        winner = select_duplicate_winner([item.record for item in remaining])
        winner_item = next(item for item in remaining if item.record.id == winner.id)
        still_remaining: list[_ScopedRecord] = []

        for item in remaining:
            if item.path == winner_item.path:
                continue

            if is_strong_duplicate(winner_item.record, item.record):
                findings.append(
                    LintFinding(
                        level="error",
                        code="duplicate-conflict",
                        subject=str(item.path),
                        message=(
                            f"{scope_label} canon record is a strong duplicate "
                            f"of {winner_item.record.id}"
                        ),
                    )
                )
            else:
                still_remaining.append(item)

        remaining = still_remaining

    return findings


def _supersedes_findings(
    records: list[_ScopedRecord],
    *,
    scope_label: str,
) -> list[LintFinding]:
    candidates = [item.record for item in records if item.state in {"canon", "archive"}]
    findings: list[LintFinding] = []

    for item in records:
        if item.state not in {"canon", "archive"}:
            continue

        if item.record.supersedes is None:
            continue

        if item.record.supersedes == item.record.id:
            findings.append(
                LintFinding(
                    level="error",
                    code="supersedes-invalid",
                    subject=str(item.path),
                    message="supersedes must not reference the same record id",
                )
            )
            continue

        if resolve_supersedes(item.record, candidates) is None:
            findings.append(
                LintFinding(
                    level="error",
                    code="supersedes-invalid",
                    subject=str(item.path),
                    message=(
                        f"supersedes does not resolve within {scope_label} "
                        "canon/archive"
                    ),
                )
            )

    return findings


def _secret_values(record: MemoryRecord) -> tuple[str, ...]:
    return (
        record.summary,
        record.details or "",
        *(record.tags or []),
        *(item.ref for item in record.evidence),
        *(item.note for item in record.evidence if item.note),
    )


def _sort_findings(findings: list[LintFinding]) -> list[LintFinding]:
    return sorted(findings, key=lambda finding: (finding.subject, finding.code))
