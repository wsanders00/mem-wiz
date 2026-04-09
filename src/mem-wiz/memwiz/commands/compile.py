from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

from memwiz.clock import CommandClock, build_command_clock
from memwiz.compiler import CompileValidationError, DigestPlan, build_digest_plans
from memwiz.fsops import (
    MemwizLockError,
    acquire_root_lock,
    atomic_replace,
    fsync_directory,
)
from memwiz.storage import initialize_root


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scope",
        choices=("workspace", "global", "all"),
        default="workspace",
    )


def run(
    args: argparse.Namespace,
    *,
    command_clock: CommandClock | None = None,
) -> int:
    clock = command_clock or build_command_clock()

    try:
        with acquire_root_lock(args.config.root):
            plans = build_digest_plans(
                args.config,
                scope=args.scope,
                generated_at=clock.timestamp(),
            )
            _ensure_scope_directories(args.config, scope=args.scope)
            _publish_digest_plans(plans)
    except CompileValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except MemwizLockError as exc:
        print(str(exc), file=sys.stderr)
        return 6
    except Exception as exc:
        print(f"Compile failed: {exc}", file=sys.stderr)
        return 1

    for plan in plans:
        print(
            "compiled\t"
            f"{plan.scope}\t"
            f"{plan.workspace_label}\t"
            f"{plan.path}\t"
            f"{plan.included_count}\t"
            f"{plan.omitted_count}"
        )

    return 0


def _ensure_scope_directories(config, *, scope: str) -> None:
    if scope in {"global", "all"}:
        initialize_root(config)

    if scope in {"workspace", "all"}:
        config.root.mkdir(parents=True, exist_ok=True)
        (config.root / "workspaces").mkdir(parents=True, exist_ok=True)
        config.workspace_inbox.mkdir(parents=True, exist_ok=True)
        config.workspace_canon.mkdir(parents=True, exist_ok=True)
        config.workspace_archive.mkdir(parents=True, exist_ok=True)
        config.workspace_cache.mkdir(parents=True, exist_ok=True)


def _publish_digest_plans(plans: list[DigestPlan]) -> None:
    staged_paths: list[tuple[Path, Path]] = []
    backup_paths: dict[Path, Path | None] = {}

    try:
        for plan in plans:
            temp_path = _write_staged_digest(plan)
            staged_paths.append((temp_path, plan.path))
        backup_paths = {
            destination: _stage_existing_digest(destination)
            for _temp_path, destination in staged_paths
        }
        applied_destinations: list[Path] = []

        try:
            for temp_path, destination in staged_paths:
                atomic_replace(temp_path, destination)
                fsync_directory(destination.parent)
                applied_destinations.append(destination)
        except Exception as exc:
            try:
                _restore_destinations(applied_destinations, backup_paths)
            except Exception as rollback_exc:
                raise rollback_exc from exc
            raise
    finally:
        _cleanup_paths(temp_path for temp_path, _destination in staged_paths)
        _cleanup_paths(
            backup_path
            for backup_path in backup_paths.values()
            if backup_path is not None
        )


def _write_staged_digest(plan: DigestPlan) -> Path:
    return _write_staged_bytes(
        plan.path,
        plan.content.encode("utf-8"),
    )


def _stage_existing_digest(destination: Path) -> Path | None:
    if not destination.exists():
        return None

    return _write_staged_bytes(destination, destination.read_bytes())


def _restore_destinations(
    destinations: list[Path],
    backup_paths: dict[Path, Path | None],
) -> None:
    for destination in reversed(destinations):
        backup_path = backup_paths[destination]

        if backup_path is None:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
            fsync_directory(destination.parent)
            continue

        atomic_replace(backup_path, destination)
        fsync_directory(destination.parent)


def _cleanup_paths(paths) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _write_staged_bytes(destination: Path, content: bytes) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    return temp_path
