from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from typing import Iterator, Optional


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
        file_descriptor = _create_lock_file(lock_path)
    except FileExistsError as exc:
        if _lock_is_stale(lock_path):
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

            try:
                file_descriptor = _create_lock_file(lock_path)
            except FileExistsError as retry_exc:
                raise MemwizLockError(f"memory root is locked: {lock_path}") from retry_exc
        else:
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


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    file_descriptor = os.open(path, flags | directory_flag)

    try:
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)


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
        fsync_directory(destination.parent)
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _create_lock_file(lock_path: Path) -> int:
    return os.open(
        lock_path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
    )


def _lock_is_stale(lock_path: Path) -> bool:
    pid = _read_lock_pid(lock_path)

    if pid is None:
        return True

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False

    return False


def _read_lock_pid(lock_path: Path) -> Optional[int]:
    try:
        lock_text = lock_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None

    if not lock_text:
        return None

    try:
        return int(lock_text)
    except ValueError:
        return None
