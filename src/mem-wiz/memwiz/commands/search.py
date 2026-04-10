from __future__ import annotations

import argparse
import sys

from memwiz.output import emit_json, search_hit_to_dict
from memwiz.retrieval import (
    CanonDecodeError,
    CanonValidationError,
    InvalidSearchQueryError,
    search_records,
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("query")
    parser.add_argument(
        "--scope",
        choices=("workspace", "global", "all"),
        default="all",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")


def run(args: argparse.Namespace) -> int:
    try:
        hits = search_records(
            args.config,
            args.query,
            scope=args.scope,
            limit=args.limit,
        )
    except InvalidSearchQueryError:
        print("Search query cannot be empty.", file=sys.stderr)
        return 2
    except (CanonDecodeError, CanonValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 5

    if args.format == "json":
        return emit_json(
            {
                "query": args.query,
                "scope": args.scope,
                "limit": args.limit,
                "hits": [search_hit_to_dict(hit) for hit in hits],
            }
        )

    if not hits:
        print("No accepted memories found.")
        return 0

    for hit in hits:
        sanitized_summary = hit.record.summary.replace("\t", " ")
        print(
            f"{hit.record.id}\t"
            f"{hit.scope}\t"
            f"{hit.workspace_label}\t"
            f"{hit.record.kind}\t"
            f"{sanitized_summary}"
        )

    return 0


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be a positive integer") from exc

    if parsed <= 0:
        raise argparse.ArgumentTypeError("limit must be a positive integer")

    return parsed
