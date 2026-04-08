from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_project_version_is_simver_compatible() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)

    assert match is not None
    assert re.fullmatch(r"\d+\.\d+(?:\.0)?", match.group(1))


def test_shipped_skill_root_is_src() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^skill_root\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)

    assert match is not None
    assert match.group(1) == "src"
    assert (REPO_ROOT / "src").is_dir()
