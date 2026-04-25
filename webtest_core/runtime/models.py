"""执行结果模型。

这些 dataclass 是报告、通知、结果合并共同使用的数据格式。它们只描述
“发生了什么”，不包含执行逻辑，因此序列化和测试都更直接。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


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

    def to_dict(self) -> dict:
        return asdict(self)


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

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["steps"] = [step.to_dict() for step in self.step_results]
        payload.pop("step_results", None)
        return payload


@dataclass
class SuiteResult:
    name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    case_results: list[CaseResult] = field(default_factory=list)
    suite_teardown_failed: bool = False
    suite_teardown_error_message: str | None = None
    suite_teardown_failure_type: FailureType | None = None

    def to_dict(self) -> dict:
        return {
            "suite": self.name,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "suite_teardown_failed": self.suite_teardown_failed,
            "suite_teardown_error_message": self.suite_teardown_error_message,
            "suite_teardown_failure_type": self.suite_teardown_failure_type,
            "cases": [case.to_dict() for case in self.case_results],
        }
