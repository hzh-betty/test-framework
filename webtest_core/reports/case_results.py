"""历史结果校验、按套件身份重跑与合并。"""

import json
from pathlib import Path
from dataclasses import asdict, fields

from pydantic import TypeAdapter, ValidationError

from webtest_core.dsl import DslValidationError
from webtest_core.redaction import Redactor
from webtest_core.runtime import CaseAttempt, CaseResult, StepResult, SuiteResult
from webtest_core.reports.io import write_json

_STEP_ADAPTER = TypeAdapter(StepResult)
_CASE_ADAPTER = TypeAdapter(CaseResult)
_ATTEMPT_ADAPTER = TypeAdapter(CaseAttempt)
_SUITE_ADAPTER = TypeAdapter(SuiteResult)


def write_case_results(path: str | Path, result: SuiteResult) -> Path:
    payload = result.to_dict()
    return write_json(path, Redactor(asdict(result)).redact(payload))


def _mapping(payload, label):
    if not isinstance(payload, dict):
        raise DslValidationError(f"{label} must be an object")
    return dict(payload)


def _boolean(payload, key, *, default=None):
    value = payload.get(key, default)
    if type(value) is not bool:
        raise DslValidationError(f"{key} must be a boolean")
    return value


def _step_from_dict(payload):
    data = _mapping(payload, "step")
    _boolean(data, "passed")
    _boolean(data, "dry_run", default=False)
    if set(data) - {field.name for field in fields(StepResult)}:
        raise DslValidationError("Unknown step result fields")
    data["children"] = [_step_from_dict(child) for child in data.get("children", [])]
    return _STEP_ADAPTER.validate_python(data)


def _case_from_dict(payload, suite_name):
    data = _mapping(payload, "case")
    _boolean(data, "passed")
    _boolean(data, "blocked", default=False)
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise DslValidationError("case name must be a non-empty string")
    if data.get("passed") and data.get("blocked"):
        raise DslValidationError("A blocked case cannot be passed")
    if set(data) - ({field.name for field in fields(CaseResult)} - {"step_results"} | {"steps"}):
        raise DslValidationError("Unknown case result fields")
    data["step_results"] = [_step_from_dict(step) for step in data.pop("steps", [])]
    data["suite"] = data.get("suite") or suite_name
    if not isinstance(data["suite"], str) or not data["suite"].strip():
        raise DslValidationError("case suite must be a non-empty string")
    attempts = []
    for attempt in data.get("attempts", []):
        attempt = _mapping(attempt, "attempt")
        _boolean(attempt, "passed")
        attempt["steps"] = [_step_from_dict(step) for step in attempt.get("steps", [])]
        if type(attempt.get("attempt")) is not int or attempt["attempt"] < 1:
            raise DslValidationError("attempt must be a positive integer")
        attempts.append(_ATTEMPT_ADAPTER.validate_python(attempt))
    data["attempts"] = attempts
    return _CASE_ADAPTER.validate_python(data)


def _suite_from_dict(payload):
    data = _mapping(payload, "suite result")
    name = data.get("suite")
    if not isinstance(name, str) or not name.strip():
        raise DslValidationError("suite must be a non-empty string")
    allowed = {"suite", "passed", "total_cases", "passed_cases", "failed_cases", "blocked_cases", "cases",
               "suite_setup_failed", "suite_teardown_failed", "setup_steps", "teardown_steps",
               "error_message", "failure_type", "notification_errors", "suites"}
    if set(data) - allowed:
        raise DslValidationError("Unknown suite result fields")
    for key in ("passed", "suite_setup_failed", "suite_teardown_failed"):
        if key in data:
            _boolean(data, key)
    cases = [_case_from_dict(case, name) for case in data.get("cases", [])]
    identities = [(case.suite, case.name) for case in cases]
    if len(set(identities)) != len(identities):
        raise DslValidationError("Duplicate case identities in results")
    result = _SUITE_ADAPTER.validate_python({"name": name, "case_results": cases,
        "setup_steps": [_step_from_dict(step) for step in data.get("setup_steps", [])],
        "teardown_steps": [_step_from_dict(step) for step in data.get("teardown_steps", [])],
        "error_message": data.get("error_message"), "failure_type": data.get("failure_type"),
        "notification_errors": data.get("notification_errors", []),
        "suite_results": [_suite_from_dict(item) for item in data.get("suites", [])]})
    valid_suites = {leaf.name for leaf in _lifecycles(result)}
    if any(case.suite not in valid_suites for case in cases):
        raise DslValidationError("case suite identity does not match its results document")
    for key, actual in (("passed", result.passed), ("suite_setup_failed", result.suite_setup_failed),
                        ("suite_teardown_failed", result.suite_teardown_failed), ("total_cases", result.total_cases),
                        ("passed_cases", result.passed_cases), ("failed_cases", result.failed_cases), ("blocked_cases", result.blocked_cases)):
        if key in data and (type(data[key]) is not type(actual) or data[key] != actual):
            raise DslValidationError(f"Inconsistent result field: {key}")
    return result


def read_case_results(path: str | Path) -> SuiteResult:
    try:
        return _suite_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError, ValidationError) as exc:
        raise DslValidationError(f"Invalid results file {path}: {exc}") from exc


def _lifecycles(result):
    if not result.suite_results:
        return [result]
    return [leaf for item in result.suite_results for leaf in _lifecycles(item)]


def read_failed_case_names(path: str | Path, *, suite_name: str) -> set[str]:
    result = read_case_results(path)
    lifecycles = [item for item in _lifecycles(result) if item.name == suite_name]
    cases = [case for case in result.case_results if case.suite == suite_name]
    if not cases and not lifecycles:
        raise DslValidationError(f"Results do not contain suite: {suite_name}")
    lifecycle_failed = any(item.error_message or item.suite_setup_failed or item.suite_teardown_failed for item in lifecycles)
    return {case.name for case in cases if not case.passed or lifecycle_failed}


def merge_case_results(paths: list[str | Path]) -> SuiteResult:
    if not paths:
        raise DslValidationError("At least one results file is required")
    cases_by_identity = {}
    lifecycles = {}
    for path in paths:
        result = read_case_results(path)
        for case in result.case_results:
            cases_by_identity[(case.suite, case.name)] = case
        for leaf in _lifecycles(result):
            lifecycles[leaf.name] = SuiteResult(leaf.name, setup_steps=leaf.setup_steps, teardown_steps=leaf.teardown_steps,
                error_message=leaf.error_message, failure_type=leaf.failure_type, notification_errors=leaf.notification_errors)
    return SuiteResult("Merged", case_results=list(cases_by_identity.values()), suite_results=list(lifecycles.values()))
