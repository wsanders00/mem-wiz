from __future__ import annotations

from pathlib import Path
import yaml


def test_init_creates_memory_root_global_directories_and_default_policy(
    tmp_path: Path,
    run_memwiz,
) -> None:
    memory_root = tmp_path / "mem-root"

    result = run_memwiz("init", "--root", str(memory_root))
    policy = yaml.safe_load((memory_root / "policy.yaml").read_text(encoding="utf-8"))

    assert result.returncode == 0
    assert memory_root.is_dir()
    assert (memory_root / "workspaces").is_dir()
    assert (memory_root / "global").is_dir()
    assert (memory_root / "global" / "canon").is_dir()
    assert (memory_root / "global" / "archive").is_dir()
    assert (memory_root / "global" / "cache").is_dir()
    assert (memory_root / "policy.yaml").is_file()
    assert policy == {
        "autonomy_profile": "balanced",
        "auto_accept_kinds": ["workflow", "constraint", "warning", "decision"],
        "require_non_agent_evidence": True,
        "global_promotion": "suggest",
        "audit_retention_days": 30,
        "max_autonomous_memories_per_day": 25,
    }
    assert not (memory_root / "global" / "inbox").exists()
    assert not (memory_root / "workspaces" / "mem-wiz").exists()


def test_init_preserves_existing_policy_yaml(tmp_path: Path, run_memwiz) -> None:
    memory_root = tmp_path / "mem-root"
    memory_root.mkdir(parents=True)
    policy_path = memory_root / "policy.yaml"
    policy_path.write_text(
        "\n".join(
            [
                "autonomy_profile: manual",
                "auto_accept_kinds:",
                "  - workflow",
                "require_non_agent_evidence: true",
                "global_promotion: disabled",
                "audit_retention_days: 7",
                "max_autonomous_memories_per_day: 5",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_memwiz("init", "--root", str(memory_root))

    assert result.returncode == 0
    assert policy_path.read_text(encoding="utf-8").startswith("autonomy_profile: manual")
