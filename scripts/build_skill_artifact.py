from __future__ import annotations

import argparse
from pathlib import Path
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "dist"
EXCLUDED_PARTS = {"tests", "ai", "__pycache__", ".pytest_cache"}
EXCLUDED_BASENAME = "pyproject.toml"


def build_skill_artifact(output_dir: Path, *, repo_root: Path | None = None) -> Path:
    resolved_repo_root = (repo_root or REPO_ROOT).resolve()
    bundle_root = resolved_repo_root / "src" / "mem-wiz"

    if not bundle_root.is_dir():
        raise FileNotFoundError(f"skill bundle root not found: {bundle_root}")

    resolved_output_dir = output_dir.resolve()

    if _is_relative_to(resolved_output_dir, bundle_root):
        raise ValueError("output_dir must be outside the skill bundle root")

    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = resolved_output_dir / f"mem-wiz-skill-{_read_version(resolved_repo_root)}.zip"

    with ZipFile(artifact_path, "w", compression=ZIP_DEFLATED) as archive:
        for source_path in sorted(bundle_root.rglob("*")):
            if source_path.is_dir() or source_path == artifact_path:
                continue

            relative_path = source_path.relative_to(bundle_root)

            if _should_exclude(relative_path):
                continue

            archive.write(source_path, relative_path.as_posix())

    return artifact_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the mem-wiz skill release artifact.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for the generated zip artifact",
    )
    args = parser.parse_args(argv)

    artifact_path = build_skill_artifact(args.output_dir)
    print(artifact_path)
    return 0


def _read_version(repo_root: Path) -> str:
    pyproject_text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    pyproject = tomllib.loads(pyproject_text)
    return pyproject["project"]["version"]


def _should_exclude(relative_path: Path) -> bool:
    parts = relative_path.parts

    if relative_path.name == EXCLUDED_BASENAME:
        return True

    if any(part in EXCLUDED_PARTS for part in parts):
        return True

    return any(part.endswith(".egg-info") for part in parts)


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
    except ValueError:
        return False

    return True


if __name__ == "__main__":
    raise SystemExit(main())
