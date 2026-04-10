from __future__ import annotations

import json
import sys
from typing import Any, Mapping, Sequence

from memwiz.compiler import DigestPlan
from memwiz.doctoring import DoctorFinding
from memwiz.models import MemoryRecord
from memwiz.retrieval import SearchHit


def emit_json(payload: Mapping[str, Any] | Sequence[Any]) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=False) + "\n")
    return 0


def search_hit_to_dict(hit: SearchHit) -> dict[str, Any]:
    return {
        "id": hit.record.id,
        "scope": hit.scope,
        "workspace": hit.workspace_label,
        "kind": hit.record.kind,
        "summary": hit.record.summary,
        "rank_bucket": hit.rank_bucket,
        "score": hit.record.score.to_dict() if hit.record.score is not None else None,
        "tags": list(hit.record.tags or []),
        "evidence_refs": [item.ref for item in hit.record.evidence],
        "provenance_summary": _provenance_summary(hit.record),
    }


def record_to_dict(record: MemoryRecord) -> dict[str, Any]:
    return record.to_dict()


def doctor_finding_to_dict(finding: DoctorFinding) -> dict[str, str]:
    return {
        "level": finding.level,
        "code": finding.code,
        "subject": finding.subject,
        "message": finding.message,
    }


def digest_plan_to_dict(plan: DigestPlan) -> dict[str, Any]:
    return {
        "scope": plan.scope,
        "workspace_label": plan.workspace_label,
        "path": str(plan.path),
        "included_count": plan.included_count,
        "omitted_count": plan.omitted_count,
    }


def _provenance_summary(record: MemoryRecord) -> str | None:
    if record.provenance is None:
        return None

    return (
        f"{record.provenance.source_workspace}:"
        f"{record.provenance.source_memory_id}"
    )
