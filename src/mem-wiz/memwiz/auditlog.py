from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping

from memwiz.config import MemwizConfig, normalize_workspace_slug
from memwiz.fsops import fsync_directory


@dataclass(frozen=True)
class AuditWriteResult:
    path: Path


def append_audit_event(
    config: MemwizConfig,
    payload: Mapping[str, Any],
) -> AuditWriteResult:
    timestamp = payload.get("timestamp")

    if not isinstance(timestamp, str) or len(timestamp) < 10:
        raise ValueError("audit payload requires timestamp")

    day_path = config.audit_root / f"{timestamp[:10]}.jsonl"
    day_path.parent.mkdir(parents=True, exist_ok=True)

    with day_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    fsync_directory(day_path.parent)
    return AuditWriteResult(path=day_path)


def read_audit_events(
    config: MemwizConfig,
    *,
    day: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    workspace: str | None = None,
    outcome: str | None = None,
    needs_user: bool | None = None,
    reason_code: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    normalized_workspace = (
        normalize_workspace_slug(workspace)
        if workspace is not None
        else None
    )

    events: list[dict[str, Any]] = []

    for path in _iter_audit_paths(
        config.audit_root,
        day=day,
        date_from=date_from,
        date_to=date_to,
    ):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue

            payload = json.loads(line)

            if not isinstance(payload, dict):
                raise ValueError(f"audit line must decode to a mapping: {path}")

            if normalized_workspace is not None and payload.get("workspace") != normalized_workspace:
                continue

            if outcome is not None and payload.get("outcome") != outcome:
                continue

            if needs_user is not None and payload.get("needs_user") is not needs_user:
                continue

            if reason_code is not None and reason_code not in payload.get("reason_codes", []):
                continue

            events.append(payload)

    if limit is not None:
        events = events[-limit:]

    return events


def _iter_audit_paths(
    audit_root: Path,
    *,
    day: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[Path]:
    if day is not None:
        path = audit_root / f"{day}.jsonl"
        return [path] if path.exists() else []

    paths = sorted(audit_root.glob("*.jsonl"))

    if date_from is not None:
        paths = [path for path in paths if path.stem >= date_from]

    if date_to is not None:
        paths = [path for path in paths if path.stem <= date_to]

    return paths
