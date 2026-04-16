from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


FailureType = Literal["action", "assertion", "timeout", "unknown"]


@dataclass(frozen=True)
class StepExecutionResult:
    action: str
    target: str
    passed: bool
    error_message: str | None = None
    call_chain: list[str] = field(default_factory=list)
    failure_type: FailureType | None = None
    duration_ms: int | None = None
    retry_attempt: int | None = None
    retry_max_retries: int | None = None
    case_attempt: int | None = None
    case_max_retries: int | None = None
    retry_trace: list[dict[str, int | str]] = field(default_factory=list)
    resolved_locator: dict[str, str] | None = None
    current_url: str | None = None


@dataclass(frozen=True)
class CaseExecutionResult:
    name: str
    passed: bool
    step_results: list[StepExecutionResult] = field(default_factory=list)
    error_message: str | None = None
    failure_type: FailureType | None = None


@dataclass(frozen=True)
class SuiteExecutionResult:
    name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    case_results: list[CaseExecutionResult] = field(default_factory=list)
    suite_teardown_failed: bool = False
    suite_teardown_error_message: str | None = None
    suite_teardown_failure_type: FailureType | None = None
