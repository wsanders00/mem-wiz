from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_exists() -> None:
    assert (REPO_ROOT / ".github" / "workflows" / "release.yml").is_file()


def test_release_workflow_runs_on_version_tags_and_uploads_zip_and_checksum() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    for fragment in (
        "tags:",
        "- 'v*'",
        "actions/checkout@v6",
        "actions/setup-python@v6",
        "python -m pytest -q",
        "scripts/build_skill_artifact.py",
        ".sha256",
        "contents: write",
        "gh release create",
        "gh release upload",
    ):
        assert fragment in workflow_text
