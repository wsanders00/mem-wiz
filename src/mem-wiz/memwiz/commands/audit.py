from __future__ import annotations

import argparse

from memwiz.output import emit_json
from memwiz.reporting import load_audit_events


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--day")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--outcome")
    parser.add_argument("--needs-user", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")


def run(args: argparse.Namespace) -> int:
    events = load_audit_events(
        args.config,
        day=args.day,
        date_from=args.date_from,
        date_to=args.date_to,
        outcome=args.outcome,
        needs_user=True if args.needs_user else None,
    )

    if args.format == "json":
        return emit_json({"events": events})

    if not events:
        print("No audit events found.")
        return 0

    for event in events:
        print(
            f"{event['timestamp']}\t"
            f"{event['workspace']}\t"
            f"{event['outcome']}\t"
            f"{event['memory_id']}\t"
            f"{event.get('needs_user', False)}"
        )

    return 0
