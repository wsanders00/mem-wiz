from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Mapping, Optional

from memwiz.commands.accept import configure_parser as configure_accept_parser
from memwiz.commands.accept import run as run_accept
from memwiz.commands.audit import configure_parser as configure_audit_parser
from memwiz.commands.audit import run as run_audit
from memwiz.commands.status import configure_parser as configure_status_parser
from memwiz.commands.status import run as run_status
from memwiz.commands.capture import configure_parser as configure_capture_parser
from memwiz.commands.capture import run as run_capture
from memwiz.commands.compile import configure_parser as configure_compile_parser
from memwiz.commands.compile import run as run_compile
from memwiz.commands.context import configure_parser as configure_context_parser
from memwiz.commands.context import run as run_context
from memwiz.commands.doctor import configure_parser as configure_doctor_parser
from memwiz.commands.doctor import run as run_doctor
from memwiz.commands.get import configure_parser as configure_get_parser
from memwiz.commands.get import run as run_get
from memwiz.commands.init import run as run_init
from memwiz.commands.lint import configure_parser as configure_lint_parser
from memwiz.commands.lint import run as run_lint
from memwiz.commands.promote import configure_parser as configure_promote_parser
from memwiz.commands.promote import run as run_promote
from memwiz.commands.prune import configure_parser as configure_prune_parser
from memwiz.commands.prune import run as run_prune
from memwiz.commands.remember import configure_parser as configure_remember_parser
from memwiz.commands.remember import run as run_remember
from memwiz.commands.search import configure_parser as configure_search_parser
from memwiz.commands.search import run as run_search
from memwiz.commands.self_update import configure_parser as configure_self_update_parser
from memwiz.commands.self_update import run as run_self_update
from memwiz.commands.score import configure_parser as configure_score_parser
from memwiz.commands.score import run as run_score
from memwiz.config import MemwizConfig, build_config

TOP_LEVEL_COMMANDS = (
    "init",
    "capture",
    "remember",
    "score",
    "accept",
    "promote",
    "lint",
    "compile",
    "search",
    "get",
    "prune",
    "doctor",
    "status",
    "audit",
    "context",
    "self-update",
)

COMMAND_HELP = {
    "init": "initialize the memory root and shared global directories",
    "capture": "capture a workspace memory candidate",
    "remember": "capture and policy-evaluate a memory for autonomous use",
    "score": "score a captured workspace memory candidate",
    "accept": "accept an eligible workspace memory into canon",
    "promote": "promote an accepted workspace memory into global canon",
    "search": "search accepted workspace and global memories",
    "get": "print one accepted memory by id",
    "lint": "validate selected memory records for integrity conflicts",
    "compile": "compile accepted canon into bounded scope digests",
    "prune": "archive structurally redundant accepted canon memories",
    "doctor": "inspect memory root, workspace, and record health",
    "status": "summarize memory health, policy, and recent autonomous activity",
    "audit": "inspect append-only autonomous audit events",
    "context": "build bounded agent wake-up context",
    "self-update": "check for and install a newer GitHub release bundle",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memwiz",
        description="memwiz command line interface",
    )
    add_shared_path_arguments(parser)
    subparsers = parser.add_subparsers(dest="command")

    for command in TOP_LEVEL_COMMANDS:
        subparser = subparsers.add_parser(
            command,
            help=COMMAND_HELP.get(command, f"{command} placeholder"),
        )
        add_shared_path_arguments(subparser, suppress_default=True)

        if command == "init":
            subparser.set_defaults(handler=run_init)
        elif command == "capture":
            configure_capture_parser(subparser)
            subparser.set_defaults(handler=run_capture)
        elif command == "remember":
            configure_remember_parser(subparser)
            subparser.set_defaults(handler=run_remember)
        elif command == "score":
            configure_score_parser(subparser)
            subparser.set_defaults(handler=run_score)
        elif command == "accept":
            configure_accept_parser(subparser)
            subparser.set_defaults(handler=run_accept)
        elif command == "promote":
            configure_promote_parser(subparser)
            subparser.set_defaults(handler=run_promote)
        elif command == "status":
            configure_status_parser(subparser)
            subparser.set_defaults(handler=run_status)
        elif command == "audit":
            configure_audit_parser(subparser)
            subparser.set_defaults(handler=run_audit)
        elif command == "lint":
            configure_lint_parser(subparser)
            subparser.set_defaults(handler=run_lint)
        elif command == "compile":
            configure_compile_parser(subparser)
            subparser.set_defaults(handler=run_compile)
        elif command == "get":
            configure_get_parser(subparser)
            subparser.set_defaults(handler=run_get)
        elif command == "search":
            configure_search_parser(subparser)
            subparser.set_defaults(handler=run_search)
        elif command == "prune":
            configure_prune_parser(subparser)
            subparser.set_defaults(handler=run_prune)
        elif command == "doctor":
            configure_doctor_parser(subparser)
            subparser.set_defaults(handler=run_doctor)
        elif command == "context":
            configure_context_parser(subparser)
            subparser.set_defaults(handler=run_context)
        elif command == "self-update":
            configure_self_update_parser(subparser)
            subparser.set_defaults(handler=run_self_update)
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
