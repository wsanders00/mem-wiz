from __future__ import annotations

import argparse

from memwiz import __version__
from memwiz.output import emit_json
from memwiz.updating import (
    DEFAULT_RELEASE_REPO,
    UpdateError,
    apply_update,
    check_for_update,
    default_bundle_root,
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether a newer GitHub release is available",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_RELEASE_REPO,
        help="GitHub repository in owner/name form",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
    )


def run(args: argparse.Namespace) -> int:
    try:
        if args.check:
            report = check_for_update(
                bundle_root=default_bundle_root(),
                current_version=__version__,
                repo=args.repo,
            )
        else:
            report = apply_update(
                bundle_root=default_bundle_root(),
                current_version=__version__,
                repo=args.repo,
            )
    except UpdateError as exc:
        print(str(exc))
        return 1

    if args.format == "json":
        emit_json(report.to_dict())
    else:
        print(report.message)

    return 0 if report.supported_install else 1
