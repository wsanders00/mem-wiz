from __future__ import annotations

import argparse

from memwiz.doctoring import run_doctor


def configure_parser(_parser: argparse.ArgumentParser) -> None:
    """Doctor v1 uses only the shared root and workspace flags."""
    pass


def run(args: argparse.Namespace) -> int:
    findings = run_doctor(args.config)

    if not findings:
        print("No doctor findings.")
        return 0

    for finding in findings:
        print(
            f"{finding.level}\t"
            f"{finding.code}\t"
            f"{finding.subject}\t"
            f"{finding.message}"
        )

    return 1
