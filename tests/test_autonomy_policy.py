from __future__ import annotations

from pathlib import Path

import pytest

from memwiz.autonomy_policy import AutonomyPolicyError, load_policy
from memwiz.config import build_config


def test_load_policy_defaults_to_balanced_when_file_missing(tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Mem Wiz", env={})

    policy = load_policy(config)

    assert policy.autonomy_profile == "balanced"
    assert policy.auto_accept_kinds == ("workflow", "constraint", "warning", "decision")
    assert policy.require_non_agent_evidence is True
    assert policy.global_promotion == "suggest"


def test_load_policy_raises_distinct_error_for_invalid_policy(tmp_path: Path) -> None:
    config = build_config(root=tmp_path, workspace="Mem Wiz", env={})
    config.policy_path.write_text("autonomy_profile: reckless\n", encoding="utf-8")

    with pytest.raises(AutonomyPolicyError, match="autonomy_profile"):
        load_policy(config)
