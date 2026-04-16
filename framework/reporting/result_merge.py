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
    step_results = case.get("step_results") or []
    if not isinstance(step_results, list):
        raise ValueError('case "step_results" must be a list when provided')
    passed = case.get("passed")
    if not isinstance(passed, bool):
        raise ValueError(f'case "passed" must be a bool, got {type(passed).__name__}')
    failure_type = _to_failure_type(case.get("failure_type"))
    return CaseExecutionResult(
        name=case["name"],
        passed=passed,
        step_results=[_to_step_result(step) for step in step_results],
        error_message=case.get("error_message"),
        failure_type=failure_type,
    )


def _to_step_result(step: dict) -> StepExecutionResult:
    if not isinstance(step, dict):
        raise ValueError("step result item must be an object")
    action = step.get("action")
    target = step.get("target")
    if not isinstance(action, str) or not isinstance(target, str):
        raise ValueError("step result must include string action and target")
    passed = step.get("passed")
    if not isinstance(passed, bool):
        raise ValueError(f'step "passed" must be a bool, got {type(passed).__name__}')
    call_chain = step.get("call_chain") or []
    if not isinstance(call_chain, list) or any(not isinstance(item, str) for item in call_chain):
        raise ValueError('step "call_chain" must be a list[str] when provided')
    failure_type = _to_failure_type(step.get("failure_type"))
    duration_ms = _to_optional_non_negative_int(step.get("duration_ms"), "duration_ms")
    retry_attempt = _to_optional_positive_int(step.get("retry_attempt"), "retry_attempt")
    retry_max_retries = _to_optional_non_negative_int(
        step.get("retry_max_retries"),
        "retry_max_retries",
    )
    case_attempt = _to_optional_positive_int(step.get("case_attempt"), "case_attempt")
    case_max_retries = _to_optional_non_negative_int(
        step.get("case_max_retries"),
        "case_max_retries",
    )
    retry_trace = _to_retry_trace(step.get("retry_trace"))
    resolved_locator = _to_resolved_locator(step.get("resolved_locator"))
    current_url = _to_optional_string(step.get("current_url"), "current_url")
    return StepExecutionResult(
        action=action,
        target=target,
        passed=passed,
        error_message=step.get("error_message"),
        call_chain=call_chain,
        failure_type=failure_type,
        duration_ms=duration_ms,
        retry_attempt=retry_attempt,
        retry_max_retries=retry_max_retries,
        case_attempt=case_attempt,
        case_max_retries=case_max_retries,
        retry_trace=retry_trace,
        resolved_locator=resolved_locator,
        current_url=current_url,
    )


def _to_failure_type(value: object) -> FailureType | None:
    if value is None:
        return None
    if value in {"action", "assertion", "timeout", "unknown"}:
        return value
    raise ValueError(
        f'failure_type must be one of "action", "assertion", "timeout", "unknown"; '
        f"got {value!r}"
    )


def _to_optional_non_negative_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    raise ValueError(f'step "{field}" must be a non-negative int when provided')


def _to_optional_positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise ValueError(f'step "{field}" must be a positive int when provided')


def _to_optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ValueError(f'step "{field}" must be a string when provided')


def _to_retry_trace(value: object) -> list[dict[str, int | str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError('step "retry_trace" must be a list when provided')
    parsed: list[dict[str, int | str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('step "retry_trace" items must be objects')
        attempt = item.get("attempt")
        status = item.get("status")
        error = item.get("error")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
            raise ValueError('step "retry_trace.attempt" must be a positive int')
        if not isinstance(status, str):
            raise ValueError('step "retry_trace.status" must be a string')
        entry: dict[str, int | str] = {"attempt": attempt, "status": status}
        if error is not None:
            if not isinstance(error, str):
                raise ValueError('step "retry_trace.error" must be a string when provided')
            entry["error"] = error
        parsed.append(entry)
    return parsed


def _to_resolved_locator(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('step "resolved_locator" must be an object when provided')
    raw = value.get("raw")
    by = value.get("by")
    locator_value = value.get("value")
    if not isinstance(raw, str) or not isinstance(by, str) or not isinstance(locator_value, str):
        raise ValueError(
            'step "resolved_locator" must include string keys: raw, by, value'
        )
    return {"raw": raw, "by": by, "value": locator_value}
