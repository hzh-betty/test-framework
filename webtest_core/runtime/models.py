"""执行历史与生命周期；计数和整体状态从结果派生。"""

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import json
from typing import Literal

from webtest_core.redaction import Redactor

FailureType = Literal["assertion", "action", "validation", "deploy", "unknown"]


def suite_identity(name: str) -> str:
    return sha256(json.dumps([name], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def case_identity(suite_name: str, name: str) -> str:
    return sha256(json.dumps([suite_name, name], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def identify_result(result, *, suite_name=None, suite_id=None):
    """在显示名称脱敏前，为结果副本补充不含原文的稳定身份。"""
    if isinstance(result, CaseResult):
        name = result.suite or suite_name
        if name is None:
            return result
        return replace(result, suite=name, suite_id=result.suite_id or suite_id or suite_identity(name),
            case_id=result.case_id or case_identity(name, result.name))
    if not isinstance(result, SuiteResult):
        return result
    children = [identify_result(item) for item in result.suite_results]
    identity = result.suite_id or suite_identity(result.name)
    suite_ids = {result.name: identity}

    def collect(item):
        suite_ids[item.name] = item.suite_id
        for child in item.suite_results:
            collect(child)

    for item in children:
        collect(item)
    cases = [identify_result(case, suite_name=result.name,
        suite_id=suite_ids.get(case.suite or result.name)) for case in result.case_results]
    return replace(result, suite_id=identity, case_results=cases, suite_results=children)


@dataclass
class StepResult:
    keyword: str
    passed: bool
    arguments: list[object] = field(default_factory=list)
    kwargs: dict[str, object] = field(default_factory=dict)
    dry_run: bool = False
    error_message: str | None = None
    failure_type: FailureType | None = None
    call_chain: list[str] = field(default_factory=list)
    duration_ms: int = 0
    retry_attempt: int = 1
    retry_max_retries: int = 0
    case_attempt: int = 1
    case_max_retries: int = 0
    retry_trace: list[dict[str, object]] = field(default_factory=list)
    resolved_locator: dict[str, str] | None = None
    current_url: str | None = None
    diagnostic_error: str | None = None
    children: list["StepResult"] = field(default_factory=list)
    start: int | None = None
    stop: int | None = None
    attachments: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(Redactor(self.kwargs).redact_result(self))


@dataclass
class CaseAttempt:
    attempt: int
    passed: bool
    steps: list[StepResult] = field(default_factory=list)
    error_message: str | None = None
    failure_type: FailureType | None = None
    start: int | None = None
    stop: int | None = None

    def to_dict(self) -> dict:
        return {"attempt": self.attempt, "passed": self.passed, "steps": [step.to_dict() for step in self.steps],
                "error_message": self.error_message, "failure_type": self.failure_type,
                "start": self.start, "stop": self.stop}


@dataclass
class CaseResult:
    name: str
    passed: bool
    step_results: list[StepResult] = field(default_factory=list)
    error_message: str | None = None
    failure_type: FailureType | None = None
    module: str | None = None
    type: str | None = None
    priority: str | None = None
    owner: str | None = None
    tags: list[str] = field(default_factory=list)
    suite: str | None = None
    blocked: bool = False
    attempts: list[CaseAttempt] = field(default_factory=list)
    start: int | None = None
    stop: int | None = None
    suite_id: str | None = None
    case_id: str | None = None

    def to_dict(self) -> dict:
        result = identify_result(self)
        return {"name": result.name, "passed": result.passed, "blocked": result.blocked, "suite": result.suite,
                "error_message": result.error_message, "failure_type": result.failure_type,
                "module": result.module, "type": result.type, "priority": result.priority, "owner": result.owner,
                "tags": result.tags, "steps": [step.to_dict() for step in result.step_results],
                "attempts": [attempt.to_dict() for attempt in result.attempts], "start": result.start, "stop": result.stop,
                "suite_id": result.suite_id, "case_id": result.case_id}


@dataclass
class SuiteResult:
    name: str
    case_results: list[CaseResult] = field(default_factory=list)
    setup_steps: list[StepResult] = field(default_factory=list)
    teardown_steps: list[StepResult] = field(default_factory=list)
    error_message: str | None = None
    failure_type: FailureType | None = None
    notification_errors: list[str] = field(default_factory=list)
    # 合并报告保留各套件的生命周期；同一套件后文件覆盖。
    suite_results: list["SuiteResult"] = field(default_factory=list)
    start: int | None = None
    stop: int | None = None
    suite_id: str | None = None

    @property
    def total_cases(self):
        return len(self.case_results)

    @property
    def passed_cases(self):
        return sum(case.passed for case in self.case_results)

    @property
    def failed_cases(self):
        return sum(not case.passed and not case.blocked for case in self.case_results)

    @property
    def blocked_cases(self):
        return sum(case.blocked for case in self.case_results)

    @property
    def suite_setup_failed(self):
        return any(not step.passed for step in self.setup_steps) or any(result.suite_setup_failed for result in self.suite_results)

    @property
    def suite_teardown_failed(self):
        return any(not step.passed for step in self.teardown_steps) or any(result.suite_teardown_failed for result in self.suite_results)

    @property
    def passed(self):
        return not (self.error_message or self.failed_cases or self.blocked_cases or self.suite_setup_failed or self.suite_teardown_failed) and all(result.passed for result in self.suite_results)

    def to_dict(self) -> dict:
        result = identify_result(self)
        return {"suite": result.name, "passed": result.passed, "total_cases": result.total_cases,
                "passed_cases": result.passed_cases, "failed_cases": result.failed_cases, "blocked_cases": result.blocked_cases,
                "suite_setup_failed": result.suite_setup_failed, "suite_teardown_failed": result.suite_teardown_failed,
                "setup_steps": [step.to_dict() for step in result.setup_steps],
                "teardown_steps": [step.to_dict() for step in result.teardown_steps],
                "error_message": result.error_message, "failure_type": result.failure_type,
                "notification_errors": result.notification_errors,
                "cases": [case.to_dict() for case in result.case_results],
                "suites": [item.to_dict() for item in result.suite_results], "start": result.start, "stop": result.stop,
                "suite_id": result.suite_id}
