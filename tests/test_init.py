from __future__ import annotations

from pathlib import Path


def test_init_creates_memory_root_and_global_directories_only(
    tmp_path: Path,
    run_memwiz,
) -> None:
    memory_root = tmp_path / "mem-root"

    result = run_memwiz("init", "--root", str(memory_root))

    assert result.returncode == 0
    assert memory_root.is_dir()
    assert (memory_root / "workspaces").is_dir()
    assert (memory_root / "global").is_dir()
    assert (memory_root / "global" / "canon").is_dir()
    assert (memory_root / "global" / "archive").is_dir()
    assert (memory_root / "global" / "cache").is_dir()
    assert not (memory_root / "global" / "inbox").exists()
    assert not (memory_root / "workspaces" / "mem-wiz").exists()
