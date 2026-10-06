"""执行历史与生命周期；计数和整体状态从结果派生。"""

from dataclasses import asdict, dataclass, field
from typing import Literal

from webtest_core.redaction import Redactor

FailureType = Literal["assertion", "action", "validation", "deploy", "unknown"]


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

    def to_dict(self) -> dict:
        return Redactor(self.kwargs).redact(asdict(self))


@dataclass
class CaseAttempt:
    attempt: int
    passed: bool
    steps: list[StepResult] = field(default_factory=list)
    error_message: str | None = None
    failure_type: FailureType | None = None

    def to_dict(self) -> dict:
        return {"attempt": self.attempt, "passed": self.passed, "steps": [step.to_dict() for step in self.steps],
                "error_message": self.error_message, "failure_type": self.failure_type}


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

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "blocked": self.blocked, "suite": self.suite,
                "error_message": self.error_message, "failure_type": self.failure_type,
                "module": self.module, "type": self.type, "priority": self.priority, "owner": self.owner,
                "tags": self.tags, "steps": [step.to_dict() for step in self.step_results],
                "attempts": [attempt.to_dict() for attempt in self.attempts]}


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
        return {"suite": self.name, "passed": self.passed, "total_cases": self.total_cases,
                "passed_cases": self.passed_cases, "failed_cases": self.failed_cases, "blocked_cases": self.blocked_cases,
                "suite_setup_failed": self.suite_setup_failed, "suite_teardown_failed": self.suite_teardown_failed,
                "setup_steps": [step.to_dict() for step in self.setup_steps],
                "teardown_steps": [step.to_dict() for step in self.teardown_steps],
                "error_message": self.error_message, "failure_type": self.failure_type,
                "notification_errors": self.notification_errors,
                "cases": [{**case.to_dict(), "suite": case.suite or self.name} for case in self.case_results],
                "suites": [result.to_dict() for result in self.suite_results]}
