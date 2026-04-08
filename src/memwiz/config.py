from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from typing import Mapping, Optional, Union


DEFAULT_ROOT_DIRNAME = ".memwiz"
ENV_ROOT = "MEMWIZ_ROOT"
ENV_WORKSPACE = "MEMWIZ_WORKSPACE"


@dataclass(frozen=True)
class MemwizConfig:
    root: Path
    workspace_slug: str
    workspace_root: Path
    workspace_inbox: Path
    workspace_canon: Path
    workspace_archive: Path
    workspace_cache: Path
    global_root: Path
    global_canon: Path
    global_archive: Path
    global_cache: Path


def resolve_memory_root(
    root: Optional[Union[str, Path]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Path:
    source = root

    if source is None:
        environment = env if env is not None else os.environ
        source = environment.get(ENV_ROOT)

    if source is None:
        return Path.home() / DEFAULT_ROOT_DIRNAME

    return Path(source).expanduser()


def normalize_workspace_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    slug = slug.strip("-")

    if not slug:
        raise ValueError("workspace slug cannot be empty")

    return slug


def resolve_workspace_slug(
    workspace: Optional[str] = None,
    *,
    cwd: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> str:
    if workspace is not None:
        return normalize_workspace_slug(workspace)

    environment = env if env is not None else os.environ
    env_workspace = environment.get(ENV_WORKSPACE)

    if env_workspace:
        return normalize_workspace_slug(env_workspace)

    working_directory = (cwd if cwd is not None else Path.cwd()).resolve()
    git_root_name = _resolve_git_root_basename(working_directory)

    if git_root_name is not None:
        return normalize_workspace_slug(git_root_name)

    return normalize_workspace_slug(working_directory.name)


def build_config(
    *,
    root: Optional[Union[str, Path]] = None,
    workspace: Optional[str] = None,
    cwd: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> MemwizConfig:
    resolved_root = resolve_memory_root(root=root, env=env)
    workspace_slug = resolve_workspace_slug(
        workspace=workspace,
        cwd=cwd,
        env=env,
    )
    workspace_root = resolved_root / "workspaces" / workspace_slug
    global_root = resolved_root / "global"

    return MemwizConfig(
        root=resolved_root,
        workspace_slug=workspace_slug,
        workspace_root=workspace_root,
        workspace_inbox=workspace_root / "inbox",
        workspace_canon=workspace_root / "canon",
        workspace_archive=workspace_root / "archive",
        workspace_cache=workspace_root / "cache",
        global_root=global_root,
        global_canon=global_root / "canon",
        global_archive=global_root / "archive",
        global_cache=global_root / "cache",
    )


def _resolve_git_root_basename(cwd: Path) -> Optional[str]:
    completed = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        return None

    git_common_dir = completed.stdout.strip()

    if not git_common_dir:
        return None

    return Path(git_common_dir).resolve().parent.name
