from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from framework.executor.models import CaseExecutionResult, SuiteExecutionResult


DIMENSIONS = ("module", "type", "priority", "owner", "tag")
UNASSIGNED = "unassigned"


def build_statistics(result: SuiteExecutionResult) -> dict:
    statistics: dict[str, object] = {
        "suite": result.name,
        "overall": _summarize_cases(result.case_results),
    }
    for dimension in DIMENSIONS:
        statistics[dimension] = _summarize_dimension(result.case_results, dimension)
    return statistics


def write_statistics(path: str | Path, result: SuiteExecutionResult) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_statistics(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def _summarize_dimension(
    cases: Iterable[CaseExecutionResult],
    dimension: str,
) -> dict[str, dict]:
    buckets: dict[str, list[CaseExecutionResult]] = {}
    for case in cases:
        for value in _dimension_values(case, dimension):
            buckets.setdefault(value, []).append(case)
    return {
        bucket: _summarize_cases(bucket_cases)
        for bucket, bucket_cases in sorted(buckets.items())
    }


def _dimension_values(case: CaseExecutionResult, dimension: str) -> list[str]:
    if dimension == "tag":
        tags = [tag.strip().lower() for tag in case.tags if tag.strip()]
        return tags or [UNASSIGNED]
    value = getattr(case, dimension)
    if not isinstance(value, str) or not value.strip():
        return [UNASSIGNED]
    return [value.strip().lower()]


def _summarize_cases(cases: Iterable[CaseExecutionResult]) -> dict:
    materialized = list(cases)
    total = len(materialized)
    passed = sum(1 for case in materialized if case.passed)
    failed = total - passed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": _pass_rate(passed, total),
        "failed_cases": [_failed_case(case) for case in materialized if not case.passed],
    }


def _pass_rate(passed: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(passed / total * 100, 2)


def _failed_case(case: CaseExecutionResult) -> dict:
    return {
        "name": case.name,
        "module": case.module or UNASSIGNED,
        "owner": case.owner or UNASSIGNED,
        "failure_type": case.failure_type or "unknown",
        "error_message": case.error_message,
    }
