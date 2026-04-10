from __future__ import annotations

import argparse
import sys

from memwiz.retrieval import (
    AmbiguousMemoryIdError,
    CanonDecodeError,
    CanonValidationError,
    InvalidMemoryIdError,
    MemoryNotFoundError,
    get_record,
)
from memwiz.serde import dump_record


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument(
        "--scope",
        choices=("workspace", "global", "all"),
        default="workspace",
    )


def run(args: argparse.Namespace) -> int:
    try:
        record = get_record(
            args.config,
            args.id,
            scope=args.scope,
        )
    except InvalidMemoryIdError:
        print(f"Invalid memory id: {args.id}", file=sys.stderr)
        return 2
    except MemoryNotFoundError:
        print(f"Accepted memory not found: {args.id.strip().lower()}", file=sys.stderr)
        return 3
    except AmbiguousMemoryIdError as exc:
        print(str(exc), file=sys.stderr)
        return 4
    except (CanonDecodeError, CanonValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 5

    sys.stdout.write(dump_record(record))
    return 0
