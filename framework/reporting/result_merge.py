from __future__ import annotations

from pathlib import Path
from typing import Sequence

from framework.executor.models import (
    CaseExecutionResult,
    FailureType,
    StepExecutionResult,
    SuiteExecutionResult,
)

from .case_results import CaseResultsPayload, read_case_results_payload


def merge_case_results(*groups: list[dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for group_index, group in enumerate(groups):
        if not isinstance(group, list):
            raise ValueError(f"group at index {group_index} must be a list")
        for case_index, case in enumerate(group):
            if not isinstance(case, dict):
                raise ValueError(
                    f"case item at group {group_index} index {case_index} must be an object"
                )
            name = case.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    f"case item at group {group_index} index {case_index} must include a string name"
                )
            merged[name] = dict(case)
    return merged


def parse_merge_results_argument(argument: str) -> list[Path]:
    entries = [entry.strip() for entry in argument.split(",")]
    if not entries or all(not entry for entry in entries):
        raise ValueError("--merge-results requires at least one file path")
    if any(not entry for entry in entries):
        raise ValueError("--merge-results contains empty file entry")
    return [Path(entry) for entry in entries]


def read_and_merge_case_results(paths: Sequence[Path]) -> list[dict]:
    payload = read_and_merge_case_results_payload(paths)
    return payload["cases"]


def read_and_merge_case_results_payload(paths: Sequence[Path]) -> CaseResultsPayload:
    if not paths:
        raise ValueError("merge-results requires at least one case-results file")
    payloads = [read_case_results_payload(path) for path in paths]
    merged = merge_case_results(*[payload["cases"] for payload in payloads])
    suite_teardown_failed = False
    suite_teardown_error_message: str | None = None
    suite_teardown_failure_type: FailureType | None = None
    for payload in payloads:
        if payload["suite_teardown_failed"]:
            suite_teardown_failed = True
            if payload["suite_teardown_error_message"] is not None:
                suite_teardown_error_message = payload["suite_teardown_error_message"]
            if payload["suite_teardown_failure_type"] is not None:
                suite_teardown_failure_type = payload["suite_teardown_failure_type"]
    if not suite_teardown_failed:
        suite_teardown_error_message = None
        suite_teardown_failure_type = None
    return {
        "cases": list(merged.values()),
        "suite_teardown_failed": suite_teardown_failed,
        "suite_teardown_error_message": suite_teardown_error_message,
        "suite_teardown_failure_type": suite_teardown_failure_type,
    }


def build_suite_result_from_merged_cases(
    cases: list[dict],
    suite_name: str = "MergedResults",
    *,
    suite_teardown_failed: bool = False,
    suite_teardown_error_message: str | None = None,
    suite_teardown_failure_type: FailureType | None = None,
) -> SuiteExecutionResult:
    validated_cases = merge_case_results(cases)
    case_results = [_to_case_result(case) for case in validated_cases.values()]
    passed_cases = sum(1 for case in case_results if case.passed)
    failed_cases = len(case_results) - passed_cases
    if not suite_teardown_failed:
        suite_teardown_error_message = None
        suite_teardown_failure_type = None
    return SuiteExecutionResult(
        name=suite_name,
        total_cases=len(case_results),
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        case_results=case_results,
        suite_teardown_failed=suite_teardown_failed,
        suite_teardown_error_message=suite_teardown_error_message,
        suite_teardown_failure_type=suite_teardown_failure_type,
    )


def load_merged_suite_result(
    paths: Sequence[Path],
    suite_name: str = "MergedResults",
) -> SuiteExecutionResult:
    merged_payload = read_and_merge_case_results_payload(paths)
    return build_suite_result_from_merged_cases(
        merged_payload["cases"],
        suite_name=suite_name,
        suite_teardown_failed=merged_payload["suite_teardown_failed"],
        suite_teardown_error_message=merged_payload["suite_teardown_error_message"],
        suite_teardown_failure_type=merged_payload["suite_teardown_failure_type"],
    )


def _to_case_result(case: dict) -> CaseExecutionResult:
