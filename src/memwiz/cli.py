from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Mapping, Optional

from memwiz.commands.accept import configure_parser as configure_accept_parser
from memwiz.commands.accept import run as run_accept
from memwiz.commands.capture import configure_parser as configure_capture_parser
from memwiz.commands.capture import run as run_capture
from memwiz.commands.init import run as run_init
from memwiz.commands.score import configure_parser as configure_score_parser
from memwiz.commands.score import run as run_score
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
    add_shared_path_arguments(parser)
    subparsers = parser.add_subparsers(dest="command")

    for command in TOP_LEVEL_COMMANDS:
        subparser = subparsers.add_parser(command, help=f"{command} placeholder")
        add_shared_path_arguments(subparser, suppress_default=True)

        if command == "init":
            subparser.set_defaults(handler=run_init)
        elif command == "capture":
            configure_capture_parser(subparser)
            subparser.set_defaults(handler=run_capture)
        elif command == "score":
            configure_score_parser(subparser)
            subparser.set_defaults(handler=run_score)
        elif command == "accept":
            configure_accept_parser(subparser)
            subparser.set_defaults(handler=run_accept)
        else:
            subparser.set_defaults(handler=_run_placeholder)

    return parser


def _run_placeholder(args: argparse.Namespace) -> int:
    print(f"{args.command} is not implemented yet.")
    return 0


def add_shared_path_arguments(
    parser: argparse.ArgumentParser,
    *,
    suppress_default: bool = False,
) -> None:
    argument_kwargs = {"default": argparse.SUPPRESS} if suppress_default else {}

    parser.add_argument(
        "--root",
        help="memory root directory",
        **argument_kwargs,
    )
    parser.add_argument(
        "--workspace",
        help="workspace slug or source name",
        **argument_kwargs,
    )


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
