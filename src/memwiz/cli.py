from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Mapping, Optional

from memwiz.config import MemwizConfig, build_config

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
    parser.add_argument(
        "--root",
        help="memory root directory",
    )
    parser.add_argument(
        "--workspace",
        help="workspace slug or source name",
    )
    subparsers = parser.add_subparsers(dest="command")

    for command in TOP_LEVEL_COMMANDS:
        subparser = subparsers.add_parser(command, help=f"{command} placeholder")
        subparser.set_defaults(handler=_run_placeholder)

    return parser


def _run_placeholder(args: argparse.Namespace) -> int:
    print(f"{args.command} is not implemented yet.")
    return 0


def resolve_config(
    args: argparse.Namespace,
    *,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[Path] = None,
) -> MemwizConfig:
    return build_config(
        root=getattr(args, "root", None),
        workspace=getattr(args, "workspace", None),
        env=env,
        cwd=cwd,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args_list = list(argv) if argv is not None else None

    if args_list == []:
        parser.print_help()
        return 0

    args = parser.parse_args(args=args_list)
    args.config = resolve_config(args)
    handler = getattr(args, "handler", None)

    if handler is None:
        parser.print_help()
        return 0

    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
