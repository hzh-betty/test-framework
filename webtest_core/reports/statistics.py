"""多维统计报告。

统计只依赖执行结果，不依赖 DSL 或浏览器。这样合并历史结果后也可以重新
生成统计数据。
"""

from __future__ import annotations

import json
from pathlib import Path

from webtest_core.runtime import CaseResult, SuiteResult


def build_statistics(result: SuiteResult) -> dict:
    stats = {"suite": result.name, "overall": _summarize(result.case_results)}
    for dimension in ("module", "type", "priority", "owner", "tag"):
        stats[dimension] = _summarize_dimension(result.case_results, dimension)
    return stats


def write_statistics(path: str | Path, result: SuiteResult) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_statistics(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _summarize(cases: list[CaseResult]) -> dict:
    total = len(cases)
    passed = sum(1 for case in cases if case.passed)
    failed = total - passed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": 0.0 if total == 0 else round(passed / total * 100, 2),
        "failed_cases": [
            {
                "name": case.name,
                "module": case.module or "unassigned",
                "owner": case.owner or "unassigned",
                "failure_type": case.failure_type or "unknown",
                "error_message": case.error_message,
            }
            for case in cases
            if not case.passed
        ],
    }


def _summarize_dimension(cases: list[CaseResult], dimension: str) -> dict:
    buckets: dict[str, list[CaseResult]] = {}
    for case in cases:
        values = case.tags if dimension == "tag" else [getattr(case, dimension) or "unassigned"]
        for value in values or ["unassigned"]:
            buckets.setdefault(str(value).lower(), []).append(case)
    return {name: _summarize(bucket) for name, bucket in sorted(buckets.items())}
