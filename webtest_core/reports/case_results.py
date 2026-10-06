"""历史结果校验、按套件身份重跑与合并。"""

import json
import re
from pathlib import Path
from dataclasses import fields, replace

from pydantic import TypeAdapter, ValidationError

from webtest_core.dsl import DslValidationError
from webtest_core.redaction import Redactor
from webtest_core.runtime import CaseAttempt, CaseResult, StepResult, SuiteResult
from webtest_core.runtime.models import case_identity, suite_identity
from webtest_core.reports.io import write_json

_STEP_ADAPTER = TypeAdapter(StepResult)
_CASE_ADAPTER = TypeAdapter(CaseResult)
_ATTEMPT_ADAPTER = TypeAdapter(CaseAttempt)
_SUITE_ADAPTER = TypeAdapter(SuiteResult)


def write_case_results(path: str | Path, result: SuiteResult, *, redactor: Redactor | None = None) -> Path:
    redactor = redactor if redactor is not None else Redactor()
    return write_json(path, redactor.redact_result(result).to_dict())


def _mapping(payload, label):
    if not isinstance(payload, dict):
        raise DslValidationError(f"{label} must be an object")
    return dict(payload)


def _boolean(payload, key, *, default=None):
    value = payload.get(key, default)
    if type(value) is not bool:
        raise DslValidationError(f"{key} must be a boolean")
    return value


def _identity(payload, key, fallback):
    value = payload.get(key)
    if value is None:
        return fallback
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise DslValidationError(f"{key} must be a lowercase SHA-256 identity")
    return value


def _case_key(case):
    return case.suite_id, case.case_id


def _validate_timing(payload, label):
    start, stop = payload.get("start"), payload.get("stop")
    for key, value in (("start", start), ("stop", stop)):
        if value is not None and (type(value) is not int or value < 0):
            raise DslValidationError(f"{label}.{key} must be a non-negative integer or null")
    if start is not None and stop is not None and stop < start:
        raise DslValidationError(f"{label}.stop must be greater than or equal to start")


def _step_from_dict(payload):
    data = _mapping(payload, "step")
    _validate_timing(data, "step")
    _boolean(data, "passed")
    _boolean(data, "dry_run", default=False)
    if set(data) - {field.name for field in fields(StepResult)}:
        raise DslValidationError("Unknown step result fields")
    for key in ("retry_attempt", "case_attempt"):
        if key in data and (type(data[key]) is not int or data[key] < 1):
            raise DslValidationError(f"{key} must be a positive integer")
    data["children"] = [_step_from_dict(child) for child in data.get("children", [])]
    _validate_passed_steps(data["passed"], data["children"], "composite step")
    return _STEP_ADAPTER.validate_python(data)


def _validate_passed_steps(passed, steps, label):
    if passed and any(not step.passed for step in steps):
        raise DslValidationError(f"A passed {label} cannot contain failed steps")


def _case_from_dict(payload, suite_name, suite_id):
    data = _mapping(payload, "case")
    _validate_timing(data, "case")
    _boolean(data, "passed")
    _boolean(data, "blocked", default=False)
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise DslValidationError("case name must be a non-empty string")
    if data.get("passed") and data.get("blocked"):
        raise DslValidationError("A blocked case cannot be passed")
    if set(data) - ({field.name for field in fields(CaseResult)} - {"step_results"} | {"steps"}):
        raise DslValidationError("Unknown case result fields")
    data["step_results"] = [_step_from_dict(step) for step in data.pop("steps", [])]
    _validate_passed_steps(data["passed"], data["step_results"], "case")
    data["suite"] = data.get("suite") or suite_name
    if not isinstance(data["suite"], str) or not data["suite"].strip():
        raise DslValidationError("case suite must be a non-empty string")
    data["suite_id"] = _identity(data, "suite_id", suite_id if data["suite"] == suite_name else suite_identity(data["suite"]))
    data["case_id"] = _identity(data, "case_id", case_identity(data["suite"], data["name"]))
    attempts = []
    for number, attempt in enumerate(data.get("attempts", []), start=1):
        attempt = _mapping(attempt, "attempt")
        _validate_timing(attempt, "attempt")
        if set(attempt) - {field.name for field in fields(CaseAttempt)}:
            raise DslValidationError("Unknown attempt result fields")
        _boolean(attempt, "passed")
        attempt["steps"] = [_step_from_dict(step) for step in attempt.get("steps", [])]
        if type(attempt.get("attempt")) is not int or attempt["attempt"] != number:
            raise DslValidationError("attempt numbers must be consecutive integers starting at 1")
        _validate_passed_steps(attempt["passed"], attempt["steps"], "attempt")
        attempts.append(_ATTEMPT_ADAPTER.validate_python(attempt))
    if attempts:
        final = attempts[-1]
        if final.passed != data["passed"] or final.steps != data["step_results"]:
            raise DslValidationError("case result must match its final attempt")
        if any(attempt.passed for attempt in attempts[:-1]):
            raise DslValidationError("Retry history cannot continue after a passed attempt")
    data["attempts"] = attempts
    return _CASE_ADAPTER.validate_python(data)


def _suite_from_dict(payload):
    data = _mapping(payload, "suite result")
    _validate_timing(data, "suite")
    name = data.get("suite")
    if not isinstance(name, str) or not name.strip():
        raise DslValidationError("suite must be a non-empty string")
    suite_id = _identity(data, "suite_id", suite_identity(name))
    allowed = {"suite", "passed", "total_cases", "passed_cases", "failed_cases", "blocked_cases", "cases",
               "suite_setup_failed", "suite_teardown_failed", "setup_steps", "teardown_steps",
               "error_message", "failure_type", "notification_errors", "suites", "start", "stop", "suite_id"}
    if set(data) - allowed:
        raise DslValidationError("Unknown suite result fields")
    for key in ("passed", "suite_setup_failed", "suite_teardown_failed"):
        if key in data:
            _boolean(data, key)
    cases = [_case_from_dict(case, name, suite_id) for case in data.get("cases", [])]
    identities = [_case_key(case) for case in cases]
    if len(set(identities)) != len(identities):
        raise DslValidationError("Duplicate case identities in results")
    result = _SUITE_ADAPTER.validate_python({"name": name, "suite_id": suite_id, "case_results": cases,
        "start": data.get("start"), "stop": data.get("stop"),
        "setup_steps": [_step_from_dict(step) for step in data.get("setup_steps", [])],
        "teardown_steps": [_step_from_dict(step) for step in data.get("teardown_steps", [])],
        "error_message": data.get("error_message"), "failure_type": data.get("failure_type"),
        "notification_errors": data.get("notification_errors", []),
        "suite_results": [_suite_from_dict(item) for item in data.get("suites", [])]})
    all_identities = [_case_key(case) for case in _all_cases(result)]
    if len(set(all_identities)) != len(all_identities):
        raise DslValidationError("Duplicate case identities in results")
    leaves = _lifecycles(result)
    valid_suites = {leaf.suite_id for leaf in leaves}
    if len(valid_suites) != len(leaves):
        raise DslValidationError("Duplicate suite identities in results")
    if any(case.suite_id not in valid_suites for case in cases):
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
    leaves = [leaf for item in result.suite_results for leaf in _lifecycles(item)]
    # 父级运行失败影响所有下级套件；展平或再合并时不能丢失此状态。
    if result.error_message or result.setup_steps or result.teardown_steps or result.notification_errors:
        leaves = [replace(leaf,
            setup_steps=[*result.setup_steps, *leaf.setup_steps],
            teardown_steps=[*leaf.teardown_steps, *result.teardown_steps],
            error_message="; ".join(message for message in (
                f"{result.name}: {result.error_message}" if result.error_message else None,
                leaf.error_message,
            ) if message) or None,
            failure_type=result.failure_type if result.error_message else leaf.failure_type,
            notification_errors=[*result.notification_errors, *leaf.notification_errors],
        ) for leaf in leaves]
    return leaves


def _all_cases(result):
    return [*result.case_results, *(case for item in result.suite_results for case in _all_cases(item))]


def read_failed_case_names(path: str | Path, *, suite_name: str, case_names: list[str] | None = None) -> set[str]:
    result = read_case_results(path)
    identity = suite_identity(suite_name)
    lifecycles = [item for item in _lifecycles(result) if item.suite_id == identity]
    cases = [case for case in _all_cases(result) if case.suite_id == identity]
    if not cases and not lifecycles:
        raise DslValidationError(f"Results do not contain suite: {suite_name}")
    lifecycle_failed = any(item.error_message or item.suite_setup_failed or item.suite_teardown_failed for item in lifecycles)
    names_by_identity = {case_identity(suite_name, name): name for name in case_names} if case_names is not None else None
    failed_names = set()
    for case in cases:
        if case.passed and not lifecycle_failed:
            continue
        if names_by_identity is not None:
            if case.case_id not in names_by_identity:
                if case.case_id != case_identity(suite_name, case.name):
                    raise DslValidationError("Cannot resolve failed case identity in the current suite")
                failed_names.add(case.name)
            else:
                failed_names.add(names_by_identity[case.case_id])
        elif "***" in case.name and case.case_id != case_identity(suite_name, case.name):
            raise DslValidationError("Redacted case names require current case_names for rerun")
        else:
            failed_names.add(case.name)
    return failed_names


def merge_case_results(paths: list[str | Path]) -> SuiteResult:
    if not paths:
        raise DslValidationError("At least one results file is required")
    cases_by_identity = {}
    lifecycles = {}
    for path in paths:
        result = read_case_results(path)
        for case in _all_cases(result):
            cases_by_identity[_case_key(case)] = case
        for leaf in _lifecycles(result):
            lifecycles[leaf.suite_id] = SuiteResult(leaf.name, setup_steps=leaf.setup_steps, teardown_steps=leaf.teardown_steps,
                error_message=leaf.error_message, failure_type=leaf.failure_type, notification_errors=leaf.notification_errors,
                start=leaf.start, stop=leaf.stop, suite_id=leaf.suite_id)
    return SuiteResult("Merged", case_results=list(cases_by_identity.values()), suite_results=list(lifecycles.values()))
