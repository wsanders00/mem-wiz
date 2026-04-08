from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@pytest.fixture
def run_memwiz(tmp_path_factory: pytest.TempPathFactory):
    bin_dir = tmp_path_factory.mktemp("memwiz-bin")
    script_path = bin_dir / "memwiz"
    script_path.write_text(
        "#!/bin/sh\n"
        "exec python3 -m memwiz.cli \"$@\"\n",
        encoding="ascii",
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(bin_dir), env.get("PATH", "")])
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    def _run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["memwiz", *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=REPO_ROOT,
        )

    return _run
