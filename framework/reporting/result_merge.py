from __future__ import annotations

from pathlib import Path
from typing import Sequence

from framework.executor.models import CaseExecutionResult, StepExecutionResult, SuiteExecutionResult

from .case_results import read_case_results


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
    if not paths:
        raise ValueError("merge-results requires at least one case-results file")
    merged = merge_case_results(*[read_case_results(path) for path in paths])
    return list(merged.values())


def build_suite_result_from_merged_cases(
    cases: list[dict],
    suite_name: str = "MergedResults",
) -> SuiteExecutionResult:
    validated_cases = merge_case_results(cases)
    case_results = [_to_case_result(case) for case in validated_cases.values()]
    passed_cases = sum(1 for case in case_results if case.passed)
    failed_cases = len(case_results) - passed_cases
    return SuiteExecutionResult(
        name=suite_name,
        total_cases=len(case_results),
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        case_results=case_results,
    )


def load_merged_suite_result(
    paths: Sequence[Path],
    suite_name: str = "MergedResults",
) -> SuiteExecutionResult:
    merged_cases = read_and_merge_case_results(paths)
    return build_suite_result_from_merged_cases(merged_cases, suite_name=suite_name)


def _to_case_result(case: dict) -> CaseExecutionResult:
    step_results = case.get("step_results") or []
    if not isinstance(step_results, list):
        raise ValueError('case "step_results" must be a list when provided')
    return CaseExecutionResult(
        name=case["name"],
        passed=bool(case.get("passed")),
        step_results=[_to_step_result(step) for step in step_results],
        error_message=case.get("error_message"),
    )


def _to_step_result(step: dict) -> StepExecutionResult:
    if not isinstance(step, dict):
        raise ValueError("step result item must be an object")
    action = step.get("action")
    target = step.get("target")
    if not isinstance(action, str) or not isinstance(target, str):
        raise ValueError("step result must include string action and target")
    return StepExecutionResult(
        action=action,
        target=target,
        passed=bool(step.get("passed")),
        error_message=step.get("error_message"),
    )
