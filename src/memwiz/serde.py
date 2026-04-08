from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from memwiz.models import MemoryRecord


def dump_record(record: MemoryRecord) -> str:
    return yaml.safe_dump(
        record.to_dict(),
        sort_keys=False,
        allow_unicode=False,
    )


def load_record(text: str) -> MemoryRecord:
    payload: Any = yaml.safe_load(text)

    if not isinstance(payload, dict):
        raise ValueError("memory record YAML must decode to a mapping")

    return MemoryRecord.from_dict(payload)


def read_record(path: Path) -> MemoryRecord:
    return load_record(path.read_text(encoding="utf-8"))


def write_record(path: Path, record: MemoryRecord) -> None:
    path.write_text(dump_record(record), encoding="utf-8")
