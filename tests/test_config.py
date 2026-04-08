from __future__ import annotations

import subprocess
from pathlib import Path

from memwiz import cli
from memwiz.config import build_config, normalize_workspace_slug, resolve_memory_root


def test_default_root_resolution_uses_home_directory() -> None:
    assert resolve_memory_root(env={}) == Path.home() / ".memwiz"


def test_memwiz_root_environment_override_is_used(tmp_path: Path) -> None:
    configured_root = tmp_path / "custom-root"

    assert resolve_memory_root(env={"MEMWIZ_ROOT": str(configured_root)}) == configured_root


def test_memwiz_workspace_environment_override_is_used(tmp_path: Path) -> None:
    config = build_config(env={"MEMWIZ_WORKSPACE": "Team Notes"}, cwd=tmp_path)

    assert config.workspace_slug == "team-notes"


def test_cli_flags_override_environment_values(tmp_path: Path) -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--root",
            str(tmp_path / "flag-root"),
            "--workspace",
            "Flag Workspace",
            "doctor",
        ]
    )

    config = cli.resolve_config(
        args,
        env={
            "MEMWIZ_ROOT": str(tmp_path / "env-root"),
            "MEMWIZ_WORKSPACE": "env-workspace",
        },
        cwd=tmp_path,
    )

    assert config.root == tmp_path / "flag-root"
    assert config.workspace_slug == "flag-workspace"


def test_cli_resolve_config_uses_process_environment_when_env_not_passed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["doctor"])

    monkeypatch.setenv("MEMWIZ_ROOT", str(tmp_path / "env-root"))
    monkeypatch.setenv("MEMWIZ_WORKSPACE", "Env Workspace")

    config = cli.resolve_config(args, cwd=tmp_path)

    assert config.root == tmp_path / "env-root"
    assert config.workspace_slug == "env-workspace"


def test_workspace_slug_uses_enclosing_git_repository_root_basename(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repository(tmp_path / "Mixed Case Repo")
    nested_directory = repo_root / "notes" / "daily"
    nested_directory.mkdir(parents=True)

    config = build_config(cwd=nested_directory, env={})

    assert config.workspace_slug == "mixed-case-repo"


def test_workspace_slug_uses_repository_root_basename_inside_git_worktree(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repository(tmp_path / "Shared Root")
    worktree_root = tmp_path / "scratch-worktree"
    _git("branch", "feature/config", cwd=repo_root)
    _git("worktree", "add", str(worktree_root), "feature/config", cwd=repo_root)
    nested_directory = worktree_root / "notes"
    nested_directory.mkdir()

    config = build_config(cwd=nested_directory, env={})

    assert config.workspace_slug == "shared-root"


def test_workspace_slug_falls_back_to_current_directory_basename_outside_git_repo(
    tmp_path: Path,
) -> None:
    workspace_directory = tmp_path / "Outside Project"
    workspace_directory.mkdir()

    config = build_config(cwd=workspace_directory, env={})

    assert config.workspace_slug == "outside-project"


def test_workspace_slug_normalization_is_lowercase_kebab_case() -> None:
    assert normalize_workspace_slug("  Mixed_CASE.workspace 99  ") == "mixed-case-workspace-99"


def test_build_config_derives_workspace_and_global_paths(tmp_path: Path) -> None:
    root = tmp_path / "mem-root"
    config = build_config(root=root, workspace="Team Notes", env={})

    assert config.workspace_root == root / "workspaces" / "team-notes"
    assert config.workspace_inbox == root / "workspaces" / "team-notes" / "inbox"
    assert config.workspace_canon == root / "workspaces" / "team-notes" / "canon"
    assert config.workspace_archive == root / "workspaces" / "team-notes" / "archive"
    assert config.workspace_cache == root / "workspaces" / "team-notes" / "cache"
    assert config.global_root == root / "global"
    assert config.global_canon == root / "global" / "canon"
    assert config.global_archive == root / "global" / "archive"
    assert config.global_cache == root / "global" / "cache"


def _init_git_repository(path: Path) -> Path:
    path.mkdir(parents=True)
    _git("init", cwd=path)
    _git("config", "user.name", "Test User", cwd=path)
    _git("config", "user.email", "test@example.com", cwd=path)
    (path / "README.md").write_text("bootstrap\n", encoding="utf-8")
    _git("add", "README.md", cwd=path)
    _git("commit", "-m", "bootstrap", cwd=path)
    return path


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
