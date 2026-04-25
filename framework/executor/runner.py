from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
import re
import time
from typing import Callable
from uuid import uuid4

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.executor.execution_control import select_cases
from framework.executor.listener import ExecutionListener
from framework.executor.models import (
    CaseExecutionResult,
    FailureType,
    StepExecutionResult,
    SuiteExecutionResult,
)
from framework.keywords import KeywordDefinition, KeywordRegistry, normalize_keyword_name
from framework.keywords.arguments import bind_keyword_arguments
from framework.keywords.web import WebKeywordLibrary
from framework.logging.runtime_logger import FailureContext
from framework.page_objects.base_page import BasePage
from framework.parser import get_parser
from framework.selenium import (
    AssertionMismatch,
    BrowserSessionError,
    LocatorError,
    WaitTimeoutError,
)
from framework.selenium.wrapper import Locator


PageFactory = Callable[[], BasePage]
VARIABLE_PATTERN = re.compile(r"\$\{([^{}]+)\}")
LOCATOR_KEYWORDS = {
    "click",
    "type text",
    "clear",
    "wait visible",
    "wait not visible",
    "wait gone",
    "wait clickable",
    "wait text",
    "assert text",
    "select",
    "hover",
    "upload file",
}


class _DryRunPage:
    def __getattr__(self, name: str):
        def _noop(*args, **kwargs):
            return None

        return _noop


class _StepExecutionError(Exception):
    def __init__(
        self,
        message: str,
        step: StepSpec,
        call_chain: list[str],
        failure_type: FailureType,
        screenshot_path: str | None = None,
    ):
        super().__init__(message)
        self.step = step
        self.call_chain = call_chain
        self.failure_type = failure_type
        self.screenshot_path = screenshot_path


@dataclass(frozen=True)
class _StepSequenceOutcome:
    failed: bool = False
    fatal: bool = False
    error_message: str | None = None
    failure_type: FailureType | None = None
    step: StepSpec | None = None
    call_chain: list[str] = field(default_factory=list)
    screenshot_path: str | None = None


@dataclass
class Executor:
    page_factory: PageFactory
    logger: object | None = None
    screenshot_dir: str = "artifacts/screenshots"
    page_source_dir: str = "artifacts/page-source"
    keyword_libraries: list[object] = field(default_factory=list)
    listeners: list[ExecutionListener] = field(default_factory=list)
    dry_run: bool = False

    def run_file(
        self,
        dsl_path: str | Path,
        include_tag_expr: str | None = None,
        exclude_tag_expr: str | None = None,
        run_empty_suite: bool = False,
        allowed_case_names: set[str] | None = None,
        workers: int = 1,
        modules: set[str] | None = None,
        case_types: set[str] | None = None,
        priorities: set[str] | None = None,
        owners: set[str] | None = None,
    ) -> SuiteExecutionResult:
        parser = get_parser(dsl_path)
        suite = parser.parse(dsl_path)
        return self.run_suite(
            suite,
            include_tag_expr=include_tag_expr,
            exclude_tag_expr=exclude_tag_expr,
            run_empty_suite=run_empty_suite,
            allowed_case_names=allowed_case_names,
            workers=workers,
            modules=modules,
            case_types=case_types,
            priorities=priorities,
            owners=owners,
        )

    def run_suite(
        self,
        suite: SuiteSpec,
        include_tag_expr: str | None = None,
        exclude_tag_expr: str | None = None,
        run_empty_suite: bool = False,
        allowed_case_names: set[str] | None = None,
        workers: int = 1,
        modules: set[str] | None = None,
        case_types: set[str] | None = None,
        priorities: set[str] | None = None,
        owners: set[str] | None = None,
    ) -> SuiteExecutionResult:
        self._notify("start_suite", suite)
        selected_cases = select_cases(
            suite.cases,
            include_expr=include_tag_expr,
            exclude_expr=exclude_tag_expr,
            allowed_case_names=allowed_case_names,
            modules=modules,
            case_types=case_types,
            priorities=priorities,
            owners=owners,
        )
        if not selected_cases and not run_empty_suite:
            raise ValueError("Suite contains no runnable cases after filtering.")

        case_results: list[CaseExecutionResult] = []
        passed = 0
        failed = 0
        variables = dict(suite.variables)
        suite_setup_outcome = self._run_steps_block(
            page=self._new_page(),
            case_name=f"{suite.name}::suite_setup",
            steps=suite.setup,
            variables=variables,
            keywords=suite.keywords,
            step_results=[],
            case_continue_on_failure=False,
            case_attempt=1,
            case_max_retries=0,
        )
        suite_teardown_outcome = _StepSequenceOutcome()

        try:
            if suite_setup_outcome.fatal:
                setup_error = self._format_case_error(
                    f"Suite setup failed: {suite_setup_outcome.error_message}",
                    suite_setup_outcome.call_chain,
                )
                for case in selected_cases:
                    case_results.append(
                        CaseExecutionResult(
                            name=case.name,
                            passed=False,
                            step_results=[],
                            error_message=setup_error,
                            failure_type=suite_setup_outcome.failure_type,
                            module=case.module,
                            type=case.type,
                            priority=case.priority,
                            owner=case.owner,
                            tags=list(case.tags),
                        )
                    )
                failed = len(selected_cases)
            elif workers <= 1 or len(selected_cases) <= 1:
                for case in selected_cases:
                    case_results.append(self._run_case(suite, case))
                passed = sum(1 for result in case_results if result.passed)
                failed = len(case_results) - passed
            else:
                ordered: list[CaseExecutionResult | None] = [None] * len(selected_cases)
