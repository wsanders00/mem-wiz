from __future__ import annotations

import argparse

from memwiz.storage import initialize_root


def run(args: argparse.Namespace) -> int:
    initialize_root(args.config)
    print(f"Initialized memwiz memory root at {args.config.root}")
    return 0
