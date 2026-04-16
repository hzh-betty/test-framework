from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from framework.executor.models import FailureType


_VALID_FAILURE_TYPES = {"action", "assertion", "timeout", "unknown"}


class CaseResultsPayload(TypedDict):
    cases: list[dict]
    suite_teardown_failed: bool
    suite_teardown_error_message: str | None
    suite_teardown_failure_type: FailureType | None


def write_case_results(
    path: Path,
    cases: list[dict],
    *,
    suite_teardown_failed: bool = False,
    suite_teardown_error_message: str | None = None,
    suite_teardown_failure_type: FailureType | None = None,
) -> Path:
    if not isinstance(suite_teardown_failed, bool):
        raise ValueError("suite_teardown_failed must be a bool")
    if suite_teardown_error_message is not None and not isinstance(
        suite_teardown_error_message, str
    ):
        raise ValueError("suite_teardown_error_message must be a string when provided")
    if suite_teardown_failure_type is not None and suite_teardown_failure_type not in _VALID_FAILURE_TYPES:
        raise ValueError(
            'suite_teardown_failure_type must be one of "action", "assertion", "timeout", '
            f'"unknown"; got {suite_teardown_failure_type!r}'
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cases": cases,
        "suite_teardown_failed": suite_teardown_failed,
        "suite_teardown_error_message": suite_teardown_error_message,
        "suite_teardown_failure_type": suite_teardown_failure_type,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def read_case_results_payload(path: Path) -> CaseResultsPayload:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("case-results payload must be a JSON object")
    if "cases" not in payload:
        raise ValueError('case-results payload is missing required "cases" key')
    cases = payload["cases"]
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case item at index {index} must be an object")
    suite_teardown_failed = payload.get("suite_teardown_failed", False)
    if not isinstance(suite_teardown_failed, bool):
        raise ValueError("suite_teardown_failed must be a bool when provided")
    suite_teardown_error_message = payload.get("suite_teardown_error_message")
    if suite_teardown_error_message is not None and not isinstance(
        suite_teardown_error_message, str
    ):
        raise ValueError("suite_teardown_error_message must be a string when provided")
    suite_teardown_failure_type = payload.get("suite_teardown_failure_type")
    if suite_teardown_failure_type is not None and suite_teardown_failure_type not in _VALID_FAILURE_TYPES:
        raise ValueError(
            'suite_teardown_failure_type must be one of "action", "assertion", "timeout", '
            f'"unknown"; got {suite_teardown_failure_type!r}'
        )
    return {
        "cases": cases,
        "suite_teardown_failed": suite_teardown_failed,
        "suite_teardown_error_message": suite_teardown_error_message,
        "suite_teardown_failure_type": suite_teardown_failure_type,
    }


def read_case_results(path: Path) -> list[dict]:
    return read_case_results_payload(path)["cases"]


def read_failed_case_names(path: Path) -> set[str]:
    failed_names: set[str] = set()
    for index, case in enumerate(read_case_results(path)):
        if "name" not in case:
            raise ValueError(f"case item at index {index} is missing required string 'name'")
        if not isinstance(case["name"], str):
            raise ValueError(f"case item at index {index} must have string 'name'")
        if "passed" not in case:
            raise ValueError(f"case item at index {index} is missing required bool 'passed'")
        if not isinstance(case["passed"], bool):
            raise ValueError(f"case item at index {index} must have bool 'passed'")
        if case["passed"] is False:
            failed_names.add(case["name"])
    return failed_names
