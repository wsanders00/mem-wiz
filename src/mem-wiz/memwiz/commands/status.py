from __future__ import annotations

import argparse

from memwiz.output import emit_json
from memwiz.reporting import build_status_payload


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("text", "json"), default="text")


def run(args: argparse.Namespace) -> int:
    payload = build_status_payload(args.config)

    if args.format == "json":
        return emit_json(payload)

    print(f"root\t{payload['root']}")
    print(f"workspace\t{payload['workspace']}")
    print(f"policy_profile\t{payload['policy_profile']}")
    print(f"workspace_inbox\t{payload['counts']['workspace_inbox']}")
    print(f"workspace_canon\t{payload['counts']['workspace_canon']}")
    print(f"review_required_count\t{payload['review_required_count']}")
    return 0
