from __future__ import annotations

import argparse
import json
import sys

from memwiz.autonomy_policy import ALLOWED_AUTONOMY_PROFILES, AutonomyPolicyError
from memwiz.models import ALLOWED_EVIDENCE_SOURCES, ALLOWED_KINDS
from memwiz.remembering import remember


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kind", required=True, choices=sorted(ALLOWED_KINDS))
    parser.add_argument("--summary", required=True)
    parser.add_argument("--details")
    parser.add_argument("--tag", dest="tags", action="append", default=[])
    parser.add_argument(
        "--evidence-source",
        required=True,
        choices=sorted(ALLOWED_EVIDENCE_SOURCES),
    )
    parser.add_argument("--evidence-ref", required=True)
    parser.add_argument("--actor-name", default="agent")
    parser.add_argument(
        "--policy-profile",
        choices=sorted(ALLOWED_AUTONOMY_PROFILES),
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")


def run(args: argparse.Namespace) -> int:
    try:
        result = remember(
            args.config,
            kind=args.kind,
            summary=args.summary,
            details=args.details,
            tags=args.tags or (),
            evidence_source=args.evidence_source,
            evidence_ref=args.evidence_ref,
            actor_name=args.actor_name,
            policy_profile=args.policy_profile,
        )
    except AutonomyPolicyError as exc:
        print(f"Remember blocked by invalid policy: {exc}", file=sys.stderr)
        return 4
    except ValueError as exc:
        print(f"Remember rejected: {exc}", file=sys.stderr)
        return 2

    _emit_result(result, output_format=args.format)

    if result.outcome == "rejected_secret_like":
        return 4

    return 0


def _emit_result(result, *, output_format: str) -> None:
    if output_format == "json":
        sys.stdout.write(json.dumps(result.to_dict(), sort_keys=False) + "\n")
        return

    fields = [result.outcome, result.memory_id]

    if result.reason_codes:
        fields.append(",".join(result.reason_codes))

    print("\t".join(fields))
