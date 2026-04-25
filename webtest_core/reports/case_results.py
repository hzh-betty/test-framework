"""case-results.json 的读写与合并。

这个文件是执行历史的稳定格式。重跑失败和结果合并都基于它工作，因此这里
只处理 JSON 结构和 ``SuiteResult`` 之间的转换。
"""

from __future__ import annotations

import json
from pathlib import Path

from webtest_core.runtime import CaseResult, StepResult, SuiteResult


def write_case_results(path: str | Path, result: SuiteResult) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def read_failed_case_names(path: str | Path) -> set[str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        case["name"]
        for case in payload.get("cases", [])
        if case.get("passed") is False and isinstance(case.get("name"), str)
    }


def merge_case_results(paths: list[str | Path]) -> SuiteResult:
    cases_by_name: dict[str, CaseResult] = {}
    suite_name = "Merged"
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        suite_name = payload.get("suite", suite_name)
        for case_payload in payload.get("cases", []):
            case = _case_from_dict(case_payload)
            cases_by_name[case.name] = case
    cases = list(cases_by_name.values())
    passed = sum(1 for case in cases if case.passed)
    return SuiteResult(
        name=suite_name,
        total_cases=len(cases),
        passed_cases=passed,
        failed_cases=len(cases) - passed,
        case_results=cases,
    )


def _case_from_dict(payload: dict) -> CaseResult:
    steps = [
        StepResult(
            keyword=step.get("keyword", ""),
            passed=bool(step.get("passed")),
            arguments=list(step.get("arguments", [])),
            kwargs=dict(step.get("kwargs", {})),
            dry_run=bool(step.get("dry_run", False)),
            error_message=step.get("error_message"),
            failure_type=step.get("failure_type"),
            call_chain=list(step.get("call_chain", [])),
            duration_ms=int(step.get("duration_ms", 0)),
            retry_attempt=int(step.get("retry_attempt", 1)),
            retry_max_retries=int(step.get("retry_max_retries", 0)),
            case_attempt=int(step.get("case_attempt", 1)),
            case_max_retries=int(step.get("case_max_retries", 0)),
            retry_trace=list(step.get("retry_trace", [])),
            resolved_locator=step.get("resolved_locator"),
            current_url=step.get("current_url"),
        )
        for step in payload.get("steps", [])
    ]
    return CaseResult(
        name=payload["name"],
        passed=bool(payload.get("passed")),
        step_results=steps,
        error_message=payload.get("error_message"),
        failure_type=payload.get("failure_type"),
        module=payload.get("module"),
        type=payload.get("type"),
        priority=payload.get("priority"),
        owner=payload.get("owner"),
        tags=list(payload.get("tags", [])),
    )
