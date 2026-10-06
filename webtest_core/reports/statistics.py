"""多维统计报告。

统计只依赖执行结果，不依赖 DSL 或浏览器。这样合并历史结果后也可以重新
生成统计数据。
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict

from webtest_core.redaction import Redactor
from webtest_core.runtime import CaseResult, SuiteResult
from webtest_core.reports.io import write_json


def build_statistics(result: SuiteResult, *, redactor: Redactor | None = None) -> dict:
    redactor = redactor or Redactor()
    redactor.collect(asdict(result))
    result = redactor.redact_result(result)
    stats = {"suite": result.name, "overall": _summarize(result.case_results), "passed": result.passed,
             "error_message": result.error_message, "failure_type": result.failure_type,
             "suite_setup_failed": result.suite_setup_failed, "suite_teardown_failed": result.suite_teardown_failed}
    for dimension in ("module", "type", "priority", "owner", "tag"):
        stats[dimension] = _summarize_dimension(result.case_results, dimension)
    return stats


def safe_statistics(result: SuiteResult, statistics: dict | None = None, *,
                    redactor: Redactor | None = None) -> dict:
    """从安全结果重建框架统计，保留并脱敏调用方提供的额外字段。"""
    redactor = redactor or Redactor()
    redactor.collect(asdict(result))
    framework_fields = {"suite", "overall", "passed", "error_message", "failure_type",
                        "suite_setup_failed", "suite_teardown_failed", "module", "type", "priority", "owner", "tag"}
    extras = {key: value for key, value in (statistics or {}).items() if key not in framework_fields}
    redactor.collect(extras)
    payload = redactor.redact(extras)
    payload.update(build_statistics(result, redactor=redactor))
    return payload


def write_statistics(path: str | Path, result: SuiteResult, *, statistics: dict | None = None,
                     redactor: Redactor | None = None) -> Path:
    return write_json(path, safe_statistics(result, statistics, redactor=redactor))


def _summarize(cases: list[CaseResult]) -> dict:
    total = len(cases)
    passed = sum(1 for case in cases if case.passed)
    blocked = sum(case.blocked for case in cases)
    failed = total - passed - blocked
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "pass_rate": 0.0 if total == 0 else round(passed / total * 100, 2),
        "failed_cases": [
            {
                "name": case.name,
                "suite": case.suite,
                "module": case.module or "unassigned",
                "owner": case.owner or "unassigned",
                "failure_type": case.failure_type or "unknown",
                "error_message": case.error_message,
            }
            for case in cases
            if not case.passed and not case.blocked
        ],
    }


def _summarize_dimension(cases: list[CaseResult], dimension: str) -> dict:
    buckets: dict[str, list[CaseResult]] = {}
    for case in cases:
        values = case.tags if dimension == "tag" else [getattr(case, dimension) or "unassigned"]
        for value in dict.fromkeys(str(value).casefold() for value in values or ["unassigned"]):
            buckets.setdefault(value, []).append(case)
    return {name: _summarize(bucket) for name, bucket in sorted(buckets.items())}
