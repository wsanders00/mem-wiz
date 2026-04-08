from __future__ import annotations

from importlib import import_module
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_TEXT = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


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


def test_shipped_skill_root_is_src() -> None:
    assert _match_toml_value("tool.memwiz", "skill_root") == "src"
    assert (REPO_ROOT / "src").is_dir()


def test_memwiz_console_script_target_resolves_to_callable() -> None:
    target = _match_toml_value("project.scripts", "memwiz")
    module_name, function_name = target.split(":", maxsplit=1)

    module = import_module(module_name)
    entrypoint = getattr(module, function_name)

    assert callable(entrypoint)
