from __future__ import annotations

from pathlib import Path

import pytest

import memwiz.fsops as fsops


def test_write_text_atomic_uses_same_directory_temp_file_before_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "canon" / "memory.yaml"
    recorded_paths: dict[str, Path] = {}
    original_replace = fsops.atomic_replace

    def recording_replace(source: Path, destination: Path) -> None:
        recorded_paths["source"] = source
        recorded_paths["destination"] = destination
        assert source.exists()
        original_replace(source, destination)

    monkeypatch.setattr(fsops, "atomic_replace", recording_replace)

    fsops.write_text_atomic(target, "summary: remember this\n")

    assert recorded_paths["source"].parent == target.parent
    assert recorded_paths["destination"] == target
    assert not recorded_paths["source"].exists()
    assert target.read_text(encoding="utf-8") == "summary: remember this\n"


def test_acquire_root_lock_creates_and_releases_lock_file(tmp_path: Path) -> None:
    root = tmp_path / "memory-root"
    lock_path = fsops.root_lock_path(root)

    with fsops.acquire_root_lock(root) as acquired_lock_path:
        assert acquired_lock_path == lock_path
        assert lock_path.exists()

    assert not lock_path.exists()


def test_root_lock_blocks_second_writer_across_scopes(tmp_path: Path) -> None:
    root = tmp_path / "memory-root"
    workspace_target = root / "workspaces" / "alpha" / "canon" / "one.yaml"
    global_target = root / "global" / "canon" / "two.yaml"

    workspace_target.parent.mkdir(parents=True)
    global_target.parent.mkdir(parents=True)

    with fsops.acquire_root_lock(root):
        fsops.write_text_atomic(workspace_target, "summary: workspace memory\n")

        with pytest.raises(fsops.MemwizLockError):
            with fsops.acquire_root_lock(root):
                fsops.write_text_atomic(global_target, "summary: global memory\n")
