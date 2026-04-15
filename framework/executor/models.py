from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StepExecutionResult:
    action: str
    target: str
    passed: bool
    error_message: str | None = None


@dataclass(frozen=True)
class CaseExecutionResult:
    name: str
    passed: bool
    step_results: list[StepExecutionResult] = field(default_factory=list)
    error_message: str | None = None


@dataclass(frozen=True)
class SuiteExecutionResult:
    name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    case_results: list[CaseExecutionResult] = field(default_factory=list)
