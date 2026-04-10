from __future__ import annotations

import argparse
import sys

from memwiz.clock import build_command_clock
from memwiz.compiler import CompileValidationError
from memwiz.output import emit_json
from memwiz.reporting import build_context_payload


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scope",
        choices=("workspace", "global", "all"),
        default="all",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")


def run(args: argparse.Namespace) -> int:
    clock = build_command_clock()

    try:
        payload = build_context_payload(
            args.config,
            scope=args.scope,
            generated_at=clock.timestamp(),
        )
    except CompileValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        return emit_json(payload)

    sys.stdout.write(payload["text"])
    return 0
