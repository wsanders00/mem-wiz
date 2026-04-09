from __future__ import annotations

import argparse
import sys

from memwiz.clock import CommandClock, build_command_clock
from memwiz.fsops import MemwizLockError, acquire_root_lock
from memwiz.pruning import apply_prune_plan, plan_prune
from memwiz.retrieval import CanonDecodeError, CanonValidationError


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scope",
        choices=("workspace", "global", "all"),
        default="workspace",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )


def run(
    args: argparse.Namespace,
    *,
    command_clock: CommandClock | None = None,
) -> int:
    clock = command_clock or build_command_clock()

    try:
        with acquire_root_lock(args.config.root):
            actions = plan_prune(args.config, scope=args.scope)

            if not actions:
                print("No prune-eligible memories found.")
                return 0

            if args.dry_run:
                _print_rows("would-archive", actions)
                return 0

            try:
                applied = apply_prune_plan(
                    args.config,
                    actions,
                    command_clock=clock,
                )
            except (CanonDecodeError, CanonValidationError):
                raise
            except Exception as exc:
                print(f"Prune failed: {exc}", file=sys.stderr)
                return 1
    except (CanonDecodeError, CanonValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 5
    except MemwizLockError as exc:
        print(str(exc), file=sys.stderr)
        return 6

    _print_rows("archived", applied)
    return 0


def _print_rows(action_label: str, actions) -> None:
    for action in actions:
        print(
            f"{action_label}\t"
            f"{action.record.id}\t"
            f"{action.scope}\t"
            f"{action.workspace_label}\t"
            f"{action.reason}"
        )
