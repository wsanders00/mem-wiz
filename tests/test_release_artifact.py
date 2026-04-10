from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from zipfile import ZipFile

import pytest

from scripts.build_skill_artifact import build_skill_artifact


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_skill_artifact_uses_bundle_contents_as_archive_root(tmp_path: Path) -> None:
    artifact_path = build_skill_artifact(output_dir=tmp_path)

    with ZipFile(artifact_path) as archive:
        names = sorted(archive.namelist())

    assert "SKILL.md" in names
    assert "memwiz/cli.py" in names
    assert "references/autonomous-capture.md" in names
    assert "references/storage-layout.md" in names
    assert "scripts/memwiz" in names
    assert not any(name.startswith("mem-wiz/") for name in names)


def test_build_skill_artifact_preserves_valid_skill_frontmatter(tmp_path: Path) -> None:
    artifact_path = build_skill_artifact(output_dir=tmp_path)

    with ZipFile(artifact_path) as archive:
        skill_text = archive.read("SKILL.md").decode("utf-8")

    lines = skill_text.splitlines()

    assert lines[0] == "---"
    assert lines[1].startswith("name: ")
    assert lines[2].startswith("description: Use when")
    assert lines[3] == "---"


def test_build_skill_artifact_excludes_dev_only_paths_anywhere_in_tree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    bundle_root = repo_root / "src" / "mem-wiz"
    nested_root = bundle_root / "memwiz" / "internal"
    (bundle_root / "memwiz").mkdir(parents=True)
    (bundle_root / "references").mkdir(parents=True)
    (bundle_root / "scripts").mkdir(parents=True)
    nested_root.mkdir(parents=True)
    (bundle_root / "SKILL.md").write_text("skill", encoding="utf-8")
    (bundle_root / "references" / "storage-layout.md").write_text("reference", encoding="utf-8")
    (bundle_root / "scripts" / "memwiz").write_text("#!/bin/sh\n", encoding="utf-8")
    (bundle_root / "memwiz" / "__init__.py").write_text("", encoding="utf-8")
    (nested_root / "keep.txt").write_text("keep", encoding="utf-8")
    (nested_root / "tests").mkdir()
    (nested_root / "tests" / "tmp.txt").write_text("x", encoding="utf-8")
    (nested_root / "ai").mkdir()
    (nested_root / "ai" / "note.md").write_text("x", encoding="utf-8")
    (nested_root / ".pytest_cache").mkdir()
    (nested_root / ".pytest_cache" / "state").write_text("x", encoding="utf-8")
    (nested_root / "__pycache__").mkdir()
    (nested_root / "__pycache__" / "cli.pyc").write_bytes(b"x")
    (nested_root / "artifact.egg-info").mkdir()
    (nested_root / "artifact.egg-info" / "PKG-INFO").write_text("x", encoding="utf-8")
    (nested_root / "pyproject.toml").write_text('[project]\nname = "nested"\n', encoding="utf-8")
    (repo_root / "pyproject.toml").write_text('[project]\nversion = "1.2.0"\n', encoding="utf-8")

    artifact_path = build_skill_artifact(output_dir=tmp_path, repo_root=repo_root)

    with ZipFile(artifact_path) as archive:
        names = sorted(archive.namelist())

    assert artifact_path.name == "mem-wiz-skill-1.2.0.zip"
    assert "SKILL.md" in names
    assert "memwiz/__init__.py" in names
    assert "memwiz/internal/keep.txt" in names
    assert "references/storage-layout.md" in names
    assert "scripts/memwiz" in names
    assert "memwiz/internal/tests/tmp.txt" not in names
    assert "memwiz/internal/ai/note.md" not in names
    assert "memwiz/internal/.pytest_cache/state" not in names
    assert "memwiz/internal/__pycache__/cli.pyc" not in names
    assert "memwiz/internal/artifact.egg-info/PKG-INFO" not in names
    assert "memwiz/internal/pyproject.toml" not in names


def test_release_builder_cli_accepts_output_dir_and_prints_artifact_path(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_skill_artifact.py"),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0

    artifact_path = Path(completed.stdout.strip())

    assert artifact_path.parent == tmp_path
    assert artifact_path.is_file()


def test_release_bundle_launcher_is_self_contained_for_first_install(tmp_path: Path) -> None:
    artifact_path = build_skill_artifact(output_dir=tmp_path)
    install_root = tmp_path / "install"

    with ZipFile(artifact_path) as archive:
        archive.extractall(install_root)

    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim_path = shim_dir / "python3"
    real_python3 = shutil.which("python3")

    assert real_python3 is not None

    shim_path.write_text(
        f"#!/bin/sh\nexec {real_python3} -S \"$@\"\n",
        encoding="utf-8",
    )
    shim_path.chmod(shim_path.stat().st_mode | stat.S_IEXEC)

    completed = subprocess.run(
        ["/bin/sh", str(install_root / "scripts" / "memwiz"), "--help"],
        cwd=install_root,
        capture_output=True,
        text=True,
        env={
            "PATH": os.pathsep.join([str(shim_dir), os.environ.get("PATH", "")]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "",
        },
    )

    assert completed.returncode == 0
    assert "memwiz command line interface" in completed.stdout


def test_build_skill_artifact_rejects_output_dir_when_it_is_inside_bundle_root(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    bundle_root = repo_root / "src" / "mem-wiz"
    output_dir = bundle_root / "artifacts-test"
    (bundle_root / "memwiz").mkdir(parents=True)
    (bundle_root / "references").mkdir(parents=True)
    (bundle_root / "scripts").mkdir(parents=True)
    (bundle_root / "SKILL.md").write_text("skill", encoding="utf-8")
    (bundle_root / "references" / "storage-layout.md").write_text("reference", encoding="utf-8")
    (bundle_root / "scripts" / "memwiz").write_text("#!/bin/sh\n", encoding="utf-8")
    (bundle_root / "memwiz" / "__init__.py").write_text("", encoding="utf-8")
    (bundle_root / "memwiz" / "keep.txt").write_text("keep", encoding="utf-8")
    (repo_root / "pyproject.toml").write_text('[project]\nversion = "2.0"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="outside the skill bundle root"):
        build_skill_artifact(output_dir=output_dir, repo_root=repo_root)


def test_build_skill_artifact_rejects_bundle_root_as_output_dir(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    bundle_root = repo_root / "src" / "mem-wiz"
    (bundle_root / "memwiz").mkdir(parents=True)
    (bundle_root / "references").mkdir(parents=True)
    (bundle_root / "scripts").mkdir(parents=True)
    (bundle_root / "SKILL.md").write_text("skill", encoding="utf-8")
    (bundle_root / "references" / "storage-layout.md").write_text("reference", encoding="utf-8")
    (bundle_root / "scripts" / "memwiz").write_text("#!/bin/sh\n", encoding="utf-8")
    (bundle_root / "memwiz" / "__init__.py").write_text("", encoding="utf-8")
    (bundle_root / "memwiz" / "keep.txt").write_text("keep", encoding="utf-8")
    (repo_root / "pyproject.toml").write_text('[project]\nversion = "2.1"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="outside the skill bundle root"):
        build_skill_artifact(output_dir=bundle_root, repo_root=repo_root)
