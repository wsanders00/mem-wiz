from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from typing import Iterator


LOCK_FILENAME = ".memwiz.lock"


class MemwizLockError(RuntimeError):
    """Raised when a mutating command cannot acquire the root lock."""


def root_lock_path(root: Path) -> Path:
    return root / LOCK_FILENAME


@contextmanager
def acquire_root_lock(root: Path) -> Iterator[Path]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root_lock_path(root)

    try:
        file_descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError as exc:
        raise MemwizLockError(f"memory root is locked: {lock_path}") from exc

    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
            handle.flush()
            os.fsync(handle.fileno())

        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def atomic_replace(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def write_text_atomic(
    destination: Path,
    content: str,
    *,
    encoding: str = "utf-8",
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(file_descriptor, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        atomic_replace(temp_path, destination)
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise
