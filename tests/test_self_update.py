from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from memwiz.cli import main
from memwiz.updating import (
    DEFAULT_RELEASE_REPO,
    UpdateError,
    apply_update,
    check_for_update,
    select_release_assets,
)


def test_select_release_assets_matches_exact_versioned_bundle_name() -> None:
    assets = [
        {
            "name": "mem-wiz-skill-0.2.0.zip",
            "browser_download_url": "https://example.test/mem-wiz-skill-0.2.0.zip",
        },
        {
            "name": "mem-wiz-skill-0.2.0.zip.sha256",
            "browser_download_url": "https://example.test/mem-wiz-skill-0.2.0.zip.sha256",
        },
        {
            "name": "mem-wiz-skill-latest.zip",
            "browser_download_url": "https://example.test/mem-wiz-skill-latest.zip",
        },
    ]

    bundle_asset, checksum_asset = select_release_assets(assets, "0.2.0")

    assert bundle_asset["name"] == "mem-wiz-skill-0.2.0.zip"
    assert checksum_asset["name"] == "mem-wiz-skill-0.2.0.zip.sha256"


def test_check_for_update_reports_noop_when_latest_matches_current(tmp_path: Path) -> None:
    bundle_root = make_bundle_root(tmp_path / "install")

    report = check_for_update(
        bundle_root=bundle_root,
        current_version="0.2.0",
        repo=DEFAULT_RELEASE_REPO,
        fetch_release=lambda repo: release_payload("0.2.0"),
    )

    assert report.current_version == "0.2.0"
    assert report.latest_version == "0.2.0"
    assert report.action == "noop"
    assert report.updated is False
    assert report.supported_install is True
    assert report.asset_name == "mem-wiz-skill-0.2.0.zip"


def test_check_for_update_refuses_development_checkout(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    bundle_root = make_bundle_root(repo_root / "src" / "mem-wiz")
    (repo_root / ".git").write_text("gitdir: /tmp/example\n", encoding="utf-8")
    (repo_root / "pyproject.toml").write_text(
        '[project]\nname = "memwiz"\nversion = "0.2.0"\n',
        encoding="utf-8",
    )

    report = check_for_update(
        bundle_root=bundle_root,
        current_version="0.1",
        repo=DEFAULT_RELEASE_REPO,
        fetch_release=lambda repo: release_payload("0.2.0"),
    )

    assert report.supported_install is False
    assert report.updated is False
    assert "development checkout" in report.message.lower()


def test_apply_update_replaces_bundle_after_valid_download(tmp_path: Path) -> None:
    bundle_root = make_bundle_root(tmp_path / "install", version="0.1", skill_text="# old skill\n")
    version = "0.2.0"
    artifact = build_artifact(version=version, skill_text="# new skill\n")
    downloads = {
        f"https://example.test/mem-wiz-skill-{version}.zip": artifact,
        f"https://example.test/mem-wiz-skill-{version}.zip.sha256": checksum_bytes(artifact),
    }

    report = apply_update(
        bundle_root=bundle_root,
        current_version="0.1",
        repo=DEFAULT_RELEASE_REPO,
        fetch_release=lambda repo: release_payload(version),
        download_asset=lambda url: downloads[url],
    )

    assert report.latest_version == "0.2.0"
    assert report.action == "update"
    assert report.updated is True
    assert report.asset_name == "mem-wiz-skill-0.2.0.zip"
    assert (bundle_root / "SKILL.md").read_text(encoding="utf-8") == "# new skill\n"


def test_apply_update_restores_backup_when_final_swap_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_root = make_bundle_root(tmp_path / "install", version="0.1", skill_text="# old skill\n")
    version = "0.2.0"
    artifact = build_artifact(version=version, skill_text="# new skill\n")
    downloads = {
        f"https://example.test/mem-wiz-skill-{version}.zip": artifact,
        f"https://example.test/mem-wiz-skill-{version}.zip.sha256": checksum_bytes(artifact),
    }
    original_replace_path = __import__("memwiz.updating", fromlist=["replace_path"]).replace_path
    failed_once = False

    def flaky_replace_path(source: Path, destination: Path) -> None:
        nonlocal failed_once
        if destination == bundle_root and not failed_once:
            failed_once = True
            raise OSError("boom")
        original_replace_path(source, destination)

    monkeypatch.setattr("memwiz.updating.replace_path", flaky_replace_path)

    with pytest.raises(UpdateError, match="restored the previous bundle"):
        apply_update(
            bundle_root=bundle_root,
            current_version="0.1",
            repo=DEFAULT_RELEASE_REPO,
            fetch_release=lambda repo: release_payload(version),
            download_asset=lambda url: downloads[url],
        )

    assert (bundle_root / "SKILL.md").read_text(encoding="utf-8") == "# old skill\n"


def test_apply_update_rejects_checksum_mismatch(tmp_path: Path) -> None:
    bundle_root = make_bundle_root(tmp_path / "install", version="0.1", skill_text="# old skill\n")
    version = "0.2.0"
    artifact = build_artifact(version=version, skill_text="# new skill\n")
    downloads = {
        f"https://example.test/mem-wiz-skill-{version}.zip": artifact,
        f"https://example.test/mem-wiz-skill-{version}.zip.sha256": b"deadbeef\n",
    }

    with pytest.raises(UpdateError, match="checksum"):
        apply_update(
            bundle_root=bundle_root,
            current_version="0.1",
            repo=DEFAULT_RELEASE_REPO,
            fetch_release=lambda repo: release_payload(version),
            download_asset=lambda url: downloads[url],
        )


def test_self_update_json_reports_noop_when_already_current(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_root = make_bundle_root(tmp_path / "install", version="0.1", skill_text="# skill\n")

    monkeypatch.setattr("memwiz.commands.self_update.default_bundle_root", lambda: bundle_root)
    monkeypatch.setattr(
        "memwiz.commands.self_update.check_for_update",
        lambda **kwargs: check_for_update(
            bundle_root=bundle_root,
            current_version="0.1",
            repo=DEFAULT_RELEASE_REPO,
            fetch_release=lambda repo: release_payload("0.1"),
        ),
    )

    exit_code = main(["self-update", "--check", "--format", "json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["action"] == "noop"
    assert payload["updated"] is False
    assert payload["supported_install"] is True


def make_bundle_root(
    path: Path,
    *,
    version: str = "0.1",
    skill_text: str = "# skill\n",
) -> Path:
    (path / "memwiz").mkdir(parents=True)
    (path / "scripts").mkdir()
    (path / "references").mkdir()
    (path / "SKILL.md").write_text(skill_text, encoding="utf-8")
    (path / "memwiz" / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    (path / "scripts" / "memwiz").write_text("#!/bin/sh\n", encoding="utf-8")
    (path / "references" / "storage-layout.md").write_text("# storage\n", encoding="utf-8")
    return path


def release_payload(version: str) -> dict[str, object]:
    return {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/{DEFAULT_RELEASE_REPO}/releases/tag/v{version}",
        "assets": [
            {
                "name": f"mem-wiz-skill-{version}.zip",
                "browser_download_url": f"https://example.test/mem-wiz-skill-{version}.zip",
            },
            {
                "name": f"mem-wiz-skill-{version}.zip.sha256",
                "browser_download_url": f"https://example.test/mem-wiz-skill-{version}.zip.sha256",
            },
        ],
    }


def build_artifact(*, version: str, skill_text: str) -> bytes:
    artifact = io.BytesIO()

    with ZipFile(artifact, "w") as archive:
        archive.writestr("SKILL.md", skill_text)
        archive.writestr("memwiz/__init__.py", f'__version__ = "{version}"\n')
        archive.writestr("scripts/memwiz", "#!/bin/sh\n")
        archive.writestr("references/storage-layout.md", "# storage\n")

    return artifact.getvalue()


def checksum_bytes(payload: bytes) -> bytes:
    return f"{hashlib.sha256(payload).hexdigest()}\n".encode("utf-8")
