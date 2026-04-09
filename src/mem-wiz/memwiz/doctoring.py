from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import yaml

from memwiz.config import MemwizConfig
from memwiz.fsops import inspect_root_lock
from memwiz.serde import load_record


@dataclass(frozen=True)
class DoctorFinding:
    level: str
    code: str
    subject: str
    message: str


def run_doctor(config: MemwizConfig) -> list[DoctorFinding]:
    if not config.root.exists():
        return [
            DoctorFinding(
                level="error",
                code="root-missing",
                subject=str(config.root),
                message="memory root does not exist",
            )
        ]

    findings: list[DoctorFinding] = []
    root_findings: list[DoctorFinding] = []
    lock_findings: list[DoctorFinding] = []
    global_path_findings: list[DoctorFinding] = []
    workspace_path_findings: list[DoctorFinding] = []
    record_findings: list[DoctorFinding] = []

    if not os.access(config.root, os.W_OK):
        root_findings.append(
            DoctorFinding(
                level="error",
                code="path-not-writable",
                subject=str(config.root),
                message="required path is not writable",
            )
        )

    lock_status = inspect_root_lock(config.root)
    if lock_status.state == "stale":
        lock_findings.append(
            DoctorFinding(
                level="warn",
                code="lock-stale",
                subject=str(lock_status.path),
                message="stale lock file can be reclaimed",
            )
        )
    elif lock_status.state == "invalid":
        lock_findings.append(
            DoctorFinding(
                level="warn",
                code="lock-invalid",
                subject=str(lock_status.path),
                message="lock file does not contain a valid pid",
            )
        )

    required_global_paths = [
        config.root / "workspaces",
        config.global_root,
        config.global_canon,
        config.global_archive,
        config.global_cache,
    ]
    global_path_findings.extend(_inspect_required_paths(required_global_paths))

    if config.workspace_root.exists():
        required_workspace_paths = [
            config.workspace_inbox,
            config.workspace_canon,
            config.workspace_archive,
            config.workspace_cache,
        ]
        workspace_path_findings.extend(_inspect_required_paths(required_workspace_paths))

    record_findings.extend(
        _inspect_record_tree(
            config.global_canon,
            expected_status="accepted",
            expected_scope="global",
            expected_workspace=None,
            area_label="global canon",
        )
    )
    record_findings.extend(
        _inspect_record_tree(
            config.global_archive,
            expected_status="archived",
            expected_scope="global",
            expected_workspace=None,
            area_label="global archive",
        )
    )

    if config.workspace_root.exists():
        record_findings.extend(
            _inspect_record_tree(
                config.workspace_canon,
                expected_status="accepted",
                expected_scope="workspace",
                expected_workspace=config.workspace_slug,
                area_label="workspace canon",
            )
        )
        record_findings.extend(
            _inspect_record_tree(
                config.workspace_archive,
                expected_status="archived",
                expected_scope="workspace",
                expected_workspace=config.workspace_slug,
                area_label="workspace archive",
            )
        )

    findings.extend(_sort_findings(root_findings))
    findings.extend(_sort_findings(lock_findings))
    findings.extend(_sort_findings(global_path_findings))
    findings.extend(_sort_findings(workspace_path_findings))
    findings.extend(_sort_findings(record_findings))
    return findings


def _inspect_required_paths(paths: list[Path]) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []

    for path in paths:
        if not path.exists():
            findings.append(
                DoctorFinding(
                    level="error",
                    code="path-missing",
                    subject=str(path),
                    message="required directory is missing",
                )
            )
            continue

        if not path.is_dir():
            findings.append(
                DoctorFinding(
                    level="error",
                    code="path-missing",
                    subject=str(path),
                    message="required directory is missing",
                )
            )
            continue

        if not os.access(path, os.W_OK):
            findings.append(
                DoctorFinding(
                    level="error",
                    code="path-not-writable",
                    subject=str(path),
                    message="required path is not writable",
                )
            )

    return findings


def _inspect_record_tree(
    tree: Path,
    *,
    expected_status: str,
    expected_scope: str,
    expected_workspace: str | None,
    area_label: str,
) -> list[DoctorFinding]:
    if not tree.exists() or not tree.is_dir():
        return []

    findings: list[DoctorFinding] = []

    for path in sorted(tree.glob("*.yaml"), key=lambda item: str(item)):
        try:
            record_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(
                DoctorFinding(
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
                DoctorFinding(
                    level="error",
                    code="record-decode",
                    subject=str(path),
                    message=f"failed to decode YAML: {exc}",
                )
            )
            continue
        except (AttributeError, TypeError, ValueError) as exc:
            findings.append(
                DoctorFinding(
                    level="error",
                    code="record-invalid",
                    subject=str(path),
                    message=f"record failed validation: {exc}",
                )
            )
            continue

        if path.stem != record.id:
            findings.append(
                DoctorFinding(
                    level="error",
                    code="record-path-mismatch",
                    subject=str(path),
                    message=f"filename stem must match record id {record.id}",
                )
            )

        if record.status != expected_status:
            findings.append(
                DoctorFinding(
                    level="error",
                    code="record-invalid",
                    subject=str(path),
                    message=f"{area_label} record must be {expected_status}, got {record.status}",
                )
            )

        if record.scope != expected_scope:
            findings.append(
                DoctorFinding(
                    level="error",
                    code="record-invalid",
                    subject=str(path),
                    message=f"{area_label} record scope must be {expected_scope}, got {record.scope}",
                )
            )

        if record.workspace != expected_workspace:
            findings.append(
                DoctorFinding(
                    level="error",
                    code="record-invalid",
                    subject=str(path),
                    message=(
                        f"{area_label} record workspace must be "
                        f"{expected_workspace}, got {record.workspace}"
                    ),
                )
            )

    return findings


def _sort_findings(findings: list[DoctorFinding]) -> list[DoctorFinding]:
    return sorted(findings, key=lambda finding: (finding.subject, finding.code))
