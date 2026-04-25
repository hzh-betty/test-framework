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
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_index = {
                        executor.submit(self._run_case, suite, case): index
                        for index, case in enumerate(selected_cases)
                    }
                    for future in as_completed(future_to_index):
                        ordered[future_to_index[future]] = future.result()
                case_results = [result for result in ordered if result is not None]
                passed = sum(1 for result in case_results if result.passed)
                failed = len(case_results) - passed
        finally:
            suite_teardown_outcome = self._run_steps_block(
                page=self._new_page(),
                case_name=f"{suite.name}::suite_teardown",
                steps=suite.teardown,
                variables=variables,
                keywords=suite.keywords,
                step_results=[],
                case_continue_on_failure=False,
                case_attempt=1,
                case_max_retries=0,
            )

        suite_teardown_error_message: str | None = None
        if suite_teardown_outcome.failed:
            suite_teardown_error_message = self._format_case_error(
                f"Suite teardown failed: {suite_teardown_outcome.error_message}",
                suite_teardown_outcome.call_chain,
            )

        result = SuiteExecutionResult(
            name=suite.name,
            total_cases=len(selected_cases),
            passed_cases=passed,
            failed_cases=failed,
            case_results=case_results,
            suite_teardown_failed=suite_teardown_outcome.failed,
            suite_teardown_error_message=suite_teardown_error_message,
            suite_teardown_failure_type=suite_teardown_outcome.failure_type,
        )
        self._notify("end_suite", suite, result)
        return result

    def _run_case(self, suite: SuiteSpec, case: CaseSpec) -> CaseExecutionResult:
        self._notify("start_case", case)
        max_retries = self._normalize_retry(case.retry)
        step_results: list[StepExecutionResult] = []
        if self.logger:
            self.logger.info(f"case_start name={case.name}")

        final_result: CaseExecutionResult | None = None
        for attempt in range(max_retries + 1):
            page = self._new_page()
            variables = dict(suite.variables)
            variables.update(case.variables)
            attempt_start = len(step_results)
            outcome = self._run_case_attempt(
                page=page,
                suite=suite,
                case=case,
                variables=variables,
                step_results=step_results,
                case_attempt=attempt + 1,
                case_max_retries=max_retries,
            )
            if not outcome.failed:
                final_result = CaseExecutionResult(
                    name=case.name,
                    passed=True,
                    step_results=step_results,
                    module=case.module,
                    type=case.type,
                    priority=case.priority,
                    owner=case.owner,
                    tags=list(case.tags),
                )
                break
            if attempt < max_retries:
                del step_results[attempt_start:]
                if self.logger and hasattr(self.logger, "info"):
                    self.logger.info(
                        f"case_retry name={case.name} attempt={attempt + 1} "
                        f"max_retries={max_retries}"
                    )
                continue
            error_message = self._format_case_error(outcome.error_message, outcome.call_chain)
            self._log_case_failure(page=page, case=case, outcome=outcome)
            final_result = CaseExecutionResult(
                name=case.name,
                passed=False,
                step_results=step_results,
                error_message=error_message,
                failure_type=outcome.failure_type,
                module=case.module,
                type=case.type,
                priority=case.priority,
                owner=case.owner,
                tags=list(case.tags),
            )
            break

        if final_result is None:
            final_result = CaseExecutionResult(
                name=case.name,
                passed=False,
                step_results=step_results,
                error_message="Case execution failed",
                failure_type="unknown",
                module=case.module,
                type=case.type,
                priority=case.priority,
                owner=case.owner,
                tags=list(case.tags),
            )
        self._notify("end_case", case, final_result)
        return final_result

    def _run_case_attempt(
        self,
        page: BasePage | _DryRunPage,
        suite: SuiteSpec,
        case: CaseSpec,
        variables: dict[str, str],
        step_results: list[StepExecutionResult],
        case_attempt: int,
        case_max_retries: int,
    ) -> _StepSequenceOutcome:
        setup = self._run_steps_block(
            page=page,
            case_name=case.name,
            steps=case.setup,
            variables=variables,
            keywords=suite.keywords,
            step_results=step_results,
            case_continue_on_failure=case.continue_on_failure,
            case_attempt=case_attempt,
            case_max_retries=case_max_retries,
        )
        steps = self._run_steps_block(
            page=page,
            case_name=case.name,
            steps=[] if setup.fatal else case.steps,
            variables=variables,
            keywords=suite.keywords,
            step_results=step_results,
            case_continue_on_failure=case.continue_on_failure,
            case_attempt=case_attempt,
            case_max_retries=case_max_retries,
        )
        teardown = self._run_steps_block(
            page=page,
            case_name=case.name,
            steps=case.teardown,
            variables=variables,
            keywords=suite.keywords,
            step_results=step_results,
            case_continue_on_failure=case.continue_on_failure,
            case_attempt=case_attempt,
            case_max_retries=case_max_retries,
        )
        return self._merge_step_outcomes(setup, steps, teardown)

    def _merge_step_outcomes(self, *outcomes: _StepSequenceOutcome) -> _StepSequenceOutcome:
        first_failure = next((outcome for outcome in outcomes if outcome.failed), None)
        return _StepSequenceOutcome(
            failed=any(outcome.failed for outcome in outcomes),
            fatal=any(outcome.fatal for outcome in outcomes),
            error_message=first_failure.error_message if first_failure else None,
            failure_type=first_failure.failure_type if first_failure else None,
            step=first_failure.step if first_failure else None,
            call_chain=list(first_failure.call_chain) if first_failure else [],
            screenshot_path=first_failure.screenshot_path if first_failure else None,
        )

    def _run_steps_block(
        self,
        page: BasePage | _DryRunPage,
        case_name: str,
        steps: list[StepSpec],
        variables: dict[str, str],
