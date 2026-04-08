from __future__ import annotations

import argparse
from typing import Iterable, Optional


TOP_LEVEL_COMMANDS = (
    "init",
    "capture",
    "score",
    "accept",
    "promote",
    "lint",
    "compile",
    "search",
    "get",
    "prune",
    "doctor",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memwiz",
        description="memwiz command line interface",
    )
    subparsers = parser.add_subparsers(dest="command")

    for command in TOP_LEVEL_COMMANDS:
        subparser = subparsers.add_parser(command, help=f"{command} placeholder")
        subparser.set_defaults(handler=_run_placeholder)

    return parser


def _run_placeholder(args: argparse.Namespace) -> int:
    print(f"{args.command} is not implemented yet.")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args_list = list(argv) if argv is not None else None

    if args_list == []:
        parser.print_help()
        return 0

    args = parser.parse_args(args=args_list)
    handler = getattr(args, "handler", None)

    if handler is None:
        parser.print_help()
        return 0

    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
