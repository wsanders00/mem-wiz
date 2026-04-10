from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Mapping

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = REPO_ROOT / "src" / "mem-wiz"

sys.dont_write_bytecode = True

if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))

from memwiz.clock import FixedClock


def read_project_script_target(script_name: str = "memwiz") -> str:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pattern = (
        r"^\[project\.scripts\]\n"
        r"(?:.+\n)*?"
        rf'^{re.escape(script_name)}\s*=\s*"([^"]+)"'
    )
    match = re.search(pattern, pyproject_text, re.MULTILINE)

    assert match is not None
    return match.group(1)


@pytest.fixture(scope="session", autouse=True)
def clean_bundle_generated_artifacts() -> None:
    for path in BUNDLE_ROOT.rglob("*"):
        if path.name in {"__pycache__", ".pytest_cache"} and path.is_dir():
            shutil.rmtree(path)
            continue

        if path.name.endswith(".egg-info") and path.is_dir():
            shutil.rmtree(path)


@pytest.fixture
def run_memwiz(tmp_path_factory: pytest.TempPathFactory):
    bin_dir = tmp_path_factory.mktemp("memwiz-bin")
    script_path = bin_dir / "memwiz"
    entrypoint_target = read_project_script_target()
    script_path.write_text(
        f"#!{sys.executable}\n"
        "from importlib import import_module\n"
        "import sys\n"
        f"TARGET = {entrypoint_target!r}\n"
        "\n"
        "module_name, function_name = TARGET.split(':', maxsplit=1)\n"
        "module = import_module(module_name)\n"
        "entrypoint = getattr(module, function_name)\n"
        "raise SystemExit(entrypoint())\n",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(bin_dir), env.get("PATH", "")])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(BUNDLE_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    def _run(
        *args: str,
        env_overrides: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        call_env = env.copy()

        if env_overrides:
            call_env.update(env_overrides)

        call_cwd = cwd if cwd is not None else REPO_ROOT

        return subprocess.run(
            ["memwiz", *args],
            capture_output=True,
            text=True,
            env=call_env,
            cwd=call_cwd,
        )

    return _run


@pytest.fixture
def make_fixed_clock():
    def _make(value: str = "2026-04-08T15:30:00Z") -> FixedClock:
        return FixedClock.from_value(value)

    return _make
