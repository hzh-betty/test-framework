from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from framework.dsl.models import _keyword_to_legacy_action


FailureType = Literal[
    "action",
    "assertion",
    "browser_session",
    "locator",
    "timeout",
    "unknown",
]


@dataclass(frozen=True, init=False)
class StepExecutionResult:
    keyword_name: str
    passed: bool
    arguments: list[object] = field(default_factory=list)
    keyword_source: str | None = None
    dry_run: bool = False
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
    screenshot_path: str | None = None
    page_source_path: str | None = None
    browser_alias: str | None = None
    page_title: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)

    def __init__(
        self,
        keyword_name: str | None = None,
        passed: bool = False,
        arguments: list[object] | None = None,
        keyword_source: str | None = None,
        dry_run: bool = False,
        error_message: str | None = None,
        call_chain: list[str] | None = None,
        failure_type: FailureType | None = None,
        duration_ms: int | None = None,
        retry_attempt: int | None = None,
        retry_max_retries: int | None = None,
        case_attempt: int | None = None,
        case_max_retries: int | None = None,
        retry_trace: list[dict[str, int | str]] | None = None,
        resolved_locator: dict[str, str] | None = None,
        current_url: str | None = None,
        screenshot_path: str | None = None,
        page_source_path: str | None = None,
        browser_alias: str | None = None,
        page_title: str | None = None,
        diagnostics: dict[str, object] | None = None,
        **legacy: object,
    ):
        action = legacy.pop("action", None)
        target = legacy.pop("target", None)
        if legacy:
            unknown = ", ".join(sorted(str(key) for key in legacy))
            raise TypeError(f"Unknown StepExecutionResult field(s): {unknown}")
        resolved_keyword = keyword_name or (str(action) if action is not None else "")
        resolved_arguments = list(arguments or [])
        if arguments is None and target is not None:
            resolved_arguments = [target]
        object.__setattr__(self, "keyword_name", resolved_keyword)
        object.__setattr__(self, "passed", passed)
        object.__setattr__(self, "arguments", resolved_arguments)
        object.__setattr__(self, "keyword_source", keyword_source)
        object.__setattr__(self, "dry_run", dry_run)
        object.__setattr__(self, "error_message", error_message)
        object.__setattr__(self, "call_chain", list(call_chain or []))
        object.__setattr__(self, "failure_type", failure_type)
        object.__setattr__(self, "duration_ms", duration_ms)
        object.__setattr__(self, "retry_attempt", retry_attempt)
        object.__setattr__(self, "retry_max_retries", retry_max_retries)
        object.__setattr__(self, "case_attempt", case_attempt)
        object.__setattr__(self, "case_max_retries", case_max_retries)
        object.__setattr__(self, "retry_trace", list(retry_trace or []))
        object.__setattr__(self, "resolved_locator", resolved_locator)
        object.__setattr__(self, "current_url", current_url)
        object.__setattr__(self, "screenshot_path", screenshot_path)
        object.__setattr__(self, "page_source_path", page_source_path)
        object.__setattr__(self, "browser_alias", browser_alias)
        object.__setattr__(self, "page_title", page_title)
        object.__setattr__(self, "diagnostics", dict(diagnostics or {}))

    @property
    def action(self) -> str:
        return _keyword_to_legacy_action(self.keyword_name)

    @property
    def target(self) -> str | None:
        if not self.arguments:
            return None
        first = self.arguments[0]
        return first if isinstance(first, str) else str(first)


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
