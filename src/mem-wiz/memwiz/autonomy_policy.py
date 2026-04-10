from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import yaml

from memwiz.config import MemwizConfig
from memwiz.fsops import write_text_atomic
from memwiz.models import ALLOWED_KINDS


ALLOWED_AUTONOMY_PROFILES = {"manual", "balanced", "aggressive"}
ALLOWED_GLOBAL_PROMOTION_MODES = {"disabled", "suggest", "auto"}
DEFAULT_AUTO_ACCEPT_KINDS = ("workflow", "constraint", "warning", "decision")
_POLICY_KEYS = {
    "autonomy_profile",
    "auto_accept_kinds",
    "require_non_agent_evidence",
    "global_promotion",
    "audit_retention_days",
    "max_autonomous_memories_per_day",
}


class AutonomyPolicyError(ValueError):
    """Raised when policy.yaml cannot be loaded safely."""


@dataclass(frozen=True)
class AutonomyPolicy:
    autonomy_profile: str = "balanced"
    auto_accept_kinds: tuple[str, ...] = DEFAULT_AUTO_ACCEPT_KINDS
    require_non_agent_evidence: bool = True
    global_promotion: str = "suggest"
    audit_retention_days: int = 30
    max_autonomous_memories_per_day: int = 25

    def __post_init__(self) -> None:
        _validate_choice(
            "autonomy_profile",
            self.autonomy_profile,
            ALLOWED_AUTONOMY_PROFILES,
        )
        _validate_choice(
            "global_promotion",
            self.global_promotion,
            ALLOWED_GLOBAL_PROMOTION_MODES,
        )
        _validate_auto_accept_kinds(self.auto_accept_kinds)
        _validate_bool("require_non_agent_evidence", self.require_non_agent_evidence)
        _validate_positive_int("audit_retention_days", self.audit_retention_days)
        _validate_positive_int(
            "max_autonomous_memories_per_day",
            self.max_autonomous_memories_per_day,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "autonomy_profile": self.autonomy_profile,
            "auto_accept_kinds": list(self.auto_accept_kinds),
            "require_non_agent_evidence": self.require_non_agent_evidence,
            "global_promotion": self.global_promotion,
            "audit_retention_days": self.audit_retention_days,
            "max_autonomous_memories_per_day": self.max_autonomous_memories_per_day,
        }


def load_policy(config: MemwizConfig) -> AutonomyPolicy:
    payload = _read_policy_payload(config.policy_path)

    if payload is None:
        return AutonomyPolicy()

    unexpected_keys = sorted(set(payload) - _POLICY_KEYS)

    if unexpected_keys:
        raise AutonomyPolicyError(
            f"unexpected policy keys: {', '.join(unexpected_keys)}"
        )

    policy_data = dict(payload)

    if "auto_accept_kinds" in policy_data:
        policy_data["auto_accept_kinds"] = _normalize_kinds(policy_data["auto_accept_kinds"])

    return AutonomyPolicy(**policy_data)


def initialize_policy_file(config: MemwizConfig) -> Path:
    if config.policy_path.exists():
        return config.policy_path

    write_text_atomic(config.policy_path, dump_policy())
    return config.policy_path


def dump_policy(policy: AutonomyPolicy | None = None) -> str:
    active_policy = policy if policy is not None else AutonomyPolicy()
    return yaml.safe_dump(
        active_policy.to_dict(),
        sort_keys=False,
        allow_unicode=False,
    )


def resolve_policy(
    config: MemwizConfig,
    *,
    policy_profile: str | None = None,
) -> AutonomyPolicy:
    policy = load_policy(config)

    if policy_profile is None:
        return policy

    return replace(policy, autonomy_profile=policy_profile)


def profile_allows_auto_accept(policy: AutonomyPolicy) -> bool:
    return policy.autonomy_profile in {"balanced", "aggressive"}


def kind_allows_auto_accept(policy: AutonomyPolicy, kind: str) -> bool:
    return kind in policy.auto_accept_kinds


def _read_policy_payload(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AutonomyPolicyError(f"unable to load policy file: {path}") from exc

    if payload is None:
        return {}

    if not isinstance(payload, dict):
        raise AutonomyPolicyError("policy file must decode to a mapping")

    return payload


def _normalize_kinds(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AutonomyPolicyError("auto_accept_kinds must be a list")

    normalized: list[str] = []

    for item in value:
        if not isinstance(item, str):
            raise AutonomyPolicyError("auto_accept_kinds entries must be strings")

        normalized.append(item)

    return tuple(dict.fromkeys(normalized))


def _validate_choice(field_name: str, value: str, choices: set[str]) -> None:
    if value not in choices:
        raise AutonomyPolicyError(f"{field_name} must be one of {sorted(choices)}")


def _validate_auto_accept_kinds(kinds: tuple[str, ...]) -> None:
    for kind in kinds:
        if kind not in ALLOWED_KINDS:
            raise AutonomyPolicyError(f"auto_accept_kinds must use {sorted(ALLOWED_KINDS)}")


def _validate_bool(field_name: str, value: Any) -> None:
    if not isinstance(value, bool):
        raise AutonomyPolicyError(f"{field_name} must be a boolean")


def _validate_positive_int(field_name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AutonomyPolicyError(f"{field_name} must be a positive integer")
