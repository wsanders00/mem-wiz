from __future__ import annotations

import configparser
from importlib import import_module
import re
from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_TEXT = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads(PYPROJECT_TEXT)
SETUP_CFG = configparser.ConfigParser()
SETUP_CFG.read(REPO_ROOT / "setup.cfg", encoding="utf-8")


def _match_toml_value(section_name: str, key: str) -> str:
    pattern = (
        rf"^\[{re.escape(section_name)}\]\n"
        rf"(?:.+\n)*?"
        rf'^{re.escape(key)}\s*=\s*"([^"]+)"'
    )
    match = re.search(pattern, PYPROJECT_TEXT, re.MULTILINE)

    assert match is not None
    return match.group(1)


def test_project_version_is_simver_compatible() -> None:
    match = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT_TEXT, re.MULTILINE)
    assert match is not None
    assert re.fullmatch(r"\d+\.\d+(?:\.0)?", match.group(1))


def test_project_requires_python_matches_baseline() -> None:
    assert _match_toml_value("project", "requires-python") == ">=3.11"


def test_shipped_skill_root_is_bundle_directory() -> None:
    assert PYPROJECT["tool"]["memwiz"]["skill_root"] == "src/mem-wiz"
    assert (REPO_ROOT / "src" / "mem-wiz").is_dir()


def test_shipped_skill_bundle_root_exists() -> None:
    assert (REPO_ROOT / "src" / "mem-wiz").is_dir()


def test_skill_bundle_root_has_required_entries() -> None:
    bundle_root = REPO_ROOT / "src" / "mem-wiz"

    assert (bundle_root / "SKILL.md").is_file()
    assert (bundle_root / "memwiz").is_dir()
    assert (bundle_root / "scripts" / "memwiz").is_file()
    assert (bundle_root / "references" / "storage-layout.md").is_file()


def test_skill_bundle_root_top_level_entries_are_allowlisted() -> None:
    bundle_root = REPO_ROOT / "src" / "mem-wiz"

    assert sorted(path.name for path in bundle_root.iterdir()) == [
        "SKILL.md",
        "memwiz",
        "references",
        "scripts",
    ]


def test_skill_bundle_root_excludes_generated_dev_artifacts() -> None:
    bundle_root = REPO_ROOT / "src" / "mem-wiz"
    forbidden_parts = {"__pycache__", ".pytest_cache", "tests", "ai"}

    for path in bundle_root.rglob("*"):
        relative_parts = path.relative_to(bundle_root).parts

        assert forbidden_parts.isdisjoint(relative_parts)
        assert "pyproject.toml" not in relative_parts
        assert not any(part.endswith(".egg-info") for part in relative_parts)


def test_runtime_package_lives_under_bundle_root() -> None:
    assert (REPO_ROOT / "src" / "mem-wiz" / "memwiz" / "cli.py").is_file()


def test_setuptools_package_dir_points_at_bundle_root() -> None:
    assert PYPROJECT["tool"]["setuptools"]["package-dir"][""] == "src/mem-wiz"


def test_setuptools_finds_packages_under_bundle_root() -> None:
    assert PYPROJECT["tool"]["setuptools"]["packages"]["find"]["where"] == ["src/mem-wiz"]


def test_egg_info_is_redirected_outside_bundle_root() -> None:
    assert SETUP_CFG["egg_info"]["egg_base"] == "src"


def test_memwiz_console_script_target_is_pinned() -> None:
    target = _match_toml_value("project.scripts", "memwiz")

    assert target == "memwiz.cli:main"


def test_memwiz_console_script_target_resolves_to_callable() -> None:
    target = _match_toml_value("project.scripts", "memwiz")
    module_name, function_name = target.split(":", maxsplit=1)

    module = import_module(module_name)
    entrypoint = getattr(module, function_name)

    assert callable(entrypoint)
