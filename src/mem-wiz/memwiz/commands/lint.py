from __future__ import annotations

import argparse

from memwiz.validation import run_lint


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scope",
        choices=("workspace", "global", "all"),
        default="workspace",
    )


def run(args: argparse.Namespace) -> int:
    findings = run_lint(args.config, scope=args.scope)

    if not findings:
        print("No lint findings.")
        return 0

    for finding in findings:
        print(
            f"{finding.level}\t"
            f"{finding.code}\t"
            f"{finding.subject}\t"
            f"{finding.message}"
        )

    return 2
