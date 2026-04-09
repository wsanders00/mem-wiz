from __future__ import annotations

from pathlib import Path

from memwiz.clock import CommandClock
from memwiz.config import MemwizConfig
from memwiz.models import Decision, MemoryRecord, normalize_memory_id
from memwiz.serde import read_record, write_record


WORKSPACE_STATES = {
    "inbox": "workspace_inbox",
    "canon": "workspace_canon",
    "archive": "workspace_archive",
}
GLOBAL_STATES = {
    "canon": "global_canon",
    "archive": "global_archive",
}


def initialize_root(config: MemwizConfig) -> None:
    config.root.mkdir(parents=True, exist_ok=True)
    (config.root / "workspaces").mkdir(parents=True, exist_ok=True)
    config.global_canon.mkdir(parents=True, exist_ok=True)
    config.global_archive.mkdir(parents=True, exist_ok=True)
    config.global_cache.mkdir(parents=True, exist_ok=True)


def write_workspace_candidate(config: MemwizConfig, record: MemoryRecord) -> Path:
    _validate_workspace_record(record, status="captured", workspace=config.workspace_slug)
    _ensure_workspace_tree(config)
    return _write_record(config.workspace_inbox, record)


def write_workspace_canon(config: MemwizConfig, record: MemoryRecord) -> Path:
    _validate_workspace_record(record, status="accepted", workspace=config.workspace_slug)
    _ensure_workspace_tree(config)
    return _write_record(config.workspace_canon, record)


def write_global_canon(config: MemwizConfig, record: MemoryRecord) -> Path:
    if record.scope != "global":
        raise ValueError("global canon only accepts global records")

    if record.status != "accepted":
        raise ValueError("global canon only accepts accepted records")

    initialize_root(config)
    return _write_record(config.global_canon, record)


def archive_workspace_record(
    config: MemwizConfig,
    record_id: str,
    *,
    archive_reason: str,
    command_clock: CommandClock,
) -> Path:
    _ensure_workspace_tree(config)
    source_path = _record_path(config.workspace_canon, record_id)
    return _archive_record(
        source_path,
        config.workspace_archive,
        archive_reason=archive_reason,
        command_clock=command_clock,
        expected_scope="workspace",
        expected_workspace=config.workspace_slug,
    )


def archive_global_record(
    config: MemwizConfig,
    record_id: str,
    *,
    archive_reason: str,
    command_clock: CommandClock,
) -> Path:
    initialize_root(config)
    source_path = _record_path(config.global_canon, record_id)
    return _archive_record(
        source_path,
        config.global_archive,
        archive_reason=archive_reason,
        command_clock=command_clock,
        expected_scope="global",
        expected_workspace=None,
    )


def list_workspace_records(config: MemwizConfig, state: str) -> list[Path]:
    directory = _directory_for_state(config, state, WORKSPACE_STATES)
    return _list_records(directory)


def list_global_records(config: MemwizConfig, state: str) -> list[Path]:
    directory = _directory_for_state(config, state, GLOBAL_STATES)
    return _list_records(directory)


def workspace_record_path(config: MemwizConfig, state: str, record_id: str) -> Path:
    directory = _directory_for_state(config, state, WORKSPACE_STATES)
    return _record_path(directory, record_id)


def global_record_path(config: MemwizConfig, state: str, record_id: str) -> Path:
    directory = _directory_for_state(config, state, GLOBAL_STATES)
    return _record_path(directory, record_id)


def _ensure_workspace_tree(config: MemwizConfig) -> None:
    config.workspace_inbox.mkdir(parents=True, exist_ok=True)
    config.workspace_canon.mkdir(parents=True, exist_ok=True)
    config.workspace_archive.mkdir(parents=True, exist_ok=True)
    config.workspace_cache.mkdir(parents=True, exist_ok=True)


def _write_record(directory: Path, record: MemoryRecord) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = _record_path(directory, record.id)
    write_record(path, record)
    return path


def _record_path(directory: Path, record_id: str) -> Path:
    normalized_id = normalize_memory_id(record_id)
    return directory / f"{normalized_id}.yaml"


def _directory_for_state(
    config: MemwizConfig,
    state: str,
    state_map: dict[str, str],
) -> Path:
    attribute_name = state_map.get(state)

    if attribute_name is None:
        raise ValueError(f"unsupported record state: {state}")

    return getattr(config, attribute_name)


def _list_records(directory: Path) -> list[Path]:
    if not directory.exists():
        return []

    return sorted(directory.glob("*.yaml"))


def _validate_workspace_record(
    record: MemoryRecord,
    *,
    status: str,
    workspace: str,
) -> None:
    if record.scope != "workspace":
        raise ValueError("workspace storage only accepts workspace records")

    if record.workspace != workspace:
        raise ValueError("record workspace does not match the selected workspace")

    if record.status != status:
        raise ValueError(f"workspace storage requires {status} records")


def _archive_record(
    source_path: Path,
    destination_dir: Path,
    *,
    archive_reason: str,
    command_clock: CommandClock,
    expected_scope: str,
    expected_workspace: str | None,
) -> Path:
    record = read_record(source_path)

    if record.status != "accepted":
        raise ValueError("archive source record must be accepted")

    if record.scope != expected_scope:
        raise ValueError(f"archive source record must be {expected_scope}")

    if expected_scope == "workspace" and record.workspace != expected_workspace:
        raise ValueError("record workspace does not match the selected workspace")

    if expected_scope == "global" and record.workspace is not None:
        raise ValueError("global records must not include workspace")

    timestamp = command_clock.timestamp()
    decision_payload = record.decision.to_dict() if record.decision is not None else {}
    decision_payload["archived_at"] = timestamp
    decision_payload["archive_reason"] = archive_reason

    archived_payload = record.to_dict()
    archived_payload["status"] = "archived"
    archived_payload["decision"] = decision_payload
    archived_payload["updated_at"] = timestamp

    archived_record = MemoryRecord.from_dict(archived_payload)
    destination_path = _write_record(destination_dir, archived_record)
    source_path.unlink()
    return destination_path
