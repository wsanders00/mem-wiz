from __future__ import annotations

import argparse

from memwiz.doctoring import run_doctor
from memwiz.output import doctor_finding_to_dict, emit_json


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """Doctor v1 uses only the shared root and workspace flags."""
    parser.add_argument("--format", choices=("text", "json"), default="text")


def run(args: argparse.Namespace) -> int:
    findings = run_doctor(args.config)

    if args.format == "json":
        emit_json({"findings": [doctor_finding_to_dict(finding) for finding in findings]})
        return 1 if findings else 0

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
