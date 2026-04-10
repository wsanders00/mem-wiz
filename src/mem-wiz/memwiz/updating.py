from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping, Sequence
from urllib.request import Request, urlopen
from zipfile import ZipFile


DEFAULT_RELEASE_REPO = "wsanders00/mem-wiz"
GITHUB_API_ROOT = "https://api.github.com"
REQUIRED_BUNDLE_ENTRIES = (
    "SKILL.md",
    "memwiz",
    "scripts/memwiz",
    "references/storage-layout.md",
)


class UpdateError(RuntimeError):
    """Raised when self-update cannot complete safely."""


@dataclass(frozen=True)
class UpdateReport:
    current_version: str
    latest_version: str | None
    repo: str
    action: str
    updated: bool
    supported_install: bool
    asset_name: str | None
    release_url: str | None
    bundle_root: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "repo": self.repo,
            "action": self.action,
            "updated": self.updated,
            "supported_install": self.supported_install,
            "asset_name": self.asset_name,
            "release_url": self.release_url,
            "bundle_root": self.bundle_root,
            "message": self.message,
        }


def default_bundle_root(package_file: Path | None = None) -> Path:
    file_path = package_file or Path(__file__)
    return file_path.resolve().parent.parent


def check_for_update(
    *,
    bundle_root: Path,
    current_version: str,
    repo: str = DEFAULT_RELEASE_REPO,
    fetch_release: Callable[[str], Mapping[str, Any]] | None = None,
) -> UpdateReport:
    supported, reason = detect_supported_install(bundle_root)
    if not supported:
        return UpdateReport(
            current_version=current_version,
            latest_version=None,
            repo=repo,
            action="check",
            updated=False,
            supported_install=False,
            asset_name=None,
            release_url=None,
            bundle_root=str(bundle_root),
            message=reason or "self-update is not supported from this installation",
        )

    payload, latest_version, bundle_asset, _checksum_asset, release_url = resolve_release(
        repo=repo,
        fetch_release=fetch_release,
    )

    if parse_version(latest_version) <= parse_version(current_version):
        return UpdateReport(
            current_version=current_version,
            latest_version=latest_version,
            repo=repo,
            action="noop",
            updated=False,
            supported_install=True,
            asset_name=bundle_asset["name"],
            release_url=release_url,
            bundle_root=str(bundle_root),
            message=f"Already up to date at {current_version}.",
        )

    return UpdateReport(
        current_version=current_version,
        latest_version=latest_version,
        repo=repo,
        action="check",
        updated=False,
        supported_install=True,
        asset_name=bundle_asset["name"],
        release_url=release_url,
        bundle_root=str(bundle_root),
        message=f"Update available: {current_version} -> {latest_version}.",
    )


def apply_update(
    *,
    bundle_root: Path,
    current_version: str,
    repo: str = DEFAULT_RELEASE_REPO,
    fetch_release: Callable[[str], Mapping[str, Any]] | None = None,
    download_asset: Callable[[str], bytes] | None = None,
) -> UpdateReport:
    report = check_for_update(
        bundle_root=bundle_root,
        current_version=current_version,
        repo=repo,
        fetch_release=fetch_release,
    )

    if not report.supported_install or report.action == "noop":
        return report

    payload, latest_version, bundle_asset, checksum_asset, release_url = resolve_release(
        repo=repo,
        fetch_release=fetch_release,
    )
    asset_name = str(bundle_asset["name"])
    fetch_bytes = download_asset or download_asset_bytes
    bundle_bytes = fetch_bytes(str(bundle_asset["browser_download_url"]))
    checksum_bytes = fetch_bytes(str(checksum_asset["browser_download_url"]))
    verify_checksum(asset_name=asset_name, payload=bundle_bytes, checksum_payload=checksum_bytes)

    stage_root = Path(
        tempfile.mkdtemp(prefix=f".{bundle_root.name}.stage-", dir=bundle_root.parent)
    )

    try:
        extract_bundle(bundle_bytes, stage_root)
        validate_bundle_root(stage_root)
        backup_root = bundle_root.parent / f".{bundle_root.name}.backup-{os.getpid()}"
        replace_path(bundle_root, backup_root)

        try:
            replace_path(stage_root, bundle_root)
        except Exception as exc:
            _cleanup_dir(stage_root)
            replace_path(backup_root, bundle_root)
            raise UpdateError(
                "self-update failed during bundle swap and restored the previous bundle"
            ) from exc

        _cleanup_dir(backup_root)
        return UpdateReport(
            current_version=current_version,
            latest_version=latest_version,
            repo=repo,
            action="update",
            updated=True,
            supported_install=True,
            asset_name=asset_name,
            release_url=release_url,
            bundle_root=str(bundle_root),
            message=f"Updated {bundle_root.name} from {current_version} to {latest_version}.",
        )
    except UpdateError:
        raise
    except Exception as exc:
        _cleanup_dir(stage_root)
        raise UpdateError(f"self-update failed: {exc}") from exc


def select_release_assets(
    assets: Sequence[Mapping[str, Any]],
    version: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    bundle_name = f"mem-wiz-skill-{version}.zip"
    checksum_name = f"{bundle_name}.sha256"
    indexed_assets = {str(asset.get("name")): asset for asset in assets}

    bundle_asset = indexed_assets.get(bundle_name)
    checksum_asset = indexed_assets.get(checksum_name)

    if bundle_asset is None or checksum_asset is None:
        raise ValueError(f"release is missing expected assets for version {version}")

    return bundle_asset, checksum_asset


def detect_supported_install(bundle_root: Path) -> tuple[bool, str | None]:
    if any(not (bundle_root / entry).exists() for entry in REQUIRED_BUNDLE_ENTRIES):
        return False, "self-update requires an unpacked mem-wiz bundle installation"

    if not os.access(bundle_root, os.W_OK):
        return False, "self-update requires a writable bundle root"

    repo_root = bundle_root.parent.parent
    if (repo_root / ".git").exists() and (repo_root / "pyproject.toml").is_file():
        return False, "self-update is not supported from a development checkout"

    return True, None


def resolve_release(
    *,
    repo: str,
    fetch_release: Callable[[str], Mapping[str, Any]] | None = None,
) -> tuple[Mapping[str, Any], str, Mapping[str, Any], Mapping[str, Any], str | None]:
    payload = dict((fetch_release or fetch_latest_release)(repo))
    latest_version = normalize_version(str(payload["tag_name"]))
    bundle_asset, checksum_asset = select_release_assets(payload.get("assets", []), latest_version)
    release_url = _string_or_none(payload.get("html_url"))
    return payload, latest_version, bundle_asset, checksum_asset, release_url


def fetch_latest_release(repo: str) -> Mapping[str, Any]:
    request = Request(
        f"{GITHUB_API_ROOT}/repos/{repo}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "memwiz-self-update",
        },
    )

    with urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def download_asset_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "memwiz-self-update"},
    )
    with urlopen(request) as response:
        return response.read()


def normalize_version(value: str) -> str:
    return value[1:] if value.startswith("v") else value


def parse_version(value: str) -> tuple[int, int, int]:
    parts = [int(part) for part in normalize_version(value).split(".")]
    if len(parts) == 2:
        parts.append(0)
    if len(parts) != 3:
        raise ValueError(f"invalid version: {value}")
    return tuple(parts)


def verify_checksum(*, asset_name: str, payload: bytes, checksum_payload: bytes) -> None:
    expected = checksum_payload.decode("utf-8").strip().split()[0]
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise UpdateError(f"downloaded {asset_name} failed checksum verification")


def extract_bundle(payload: bytes, output_dir: Path) -> None:
    with ZipFile(io.BytesIO(payload)) as archive:
        for entry in archive.infolist():
            destination = output_dir / entry.filename

            if entry.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                _apply_entry_mode(destination, entry)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)

            with archive.open(entry) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)

            _apply_entry_mode(destination, entry)


def validate_bundle_root(bundle_root: Path) -> None:
    missing = [entry for entry in REQUIRED_BUNDLE_ENTRIES if not (bundle_root / entry).exists()]
    if missing:
        missing_text = ", ".join(missing)
        raise UpdateError(f"downloaded bundle is missing required entries: {missing_text}")


def replace_path(source: Path, destination: Path) -> None:
    source.replace(destination)


def _apply_entry_mode(path: Path, entry: Any) -> None:
    mode = int(getattr(entry, "external_attr", 0)) >> 16
    if mode:
        os.chmod(path, mode)


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _cleanup_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
