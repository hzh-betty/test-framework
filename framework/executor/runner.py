from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
import re
import time
from typing import Callable
from uuid import uuid4

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.executor.action_registry import ActionRegistry, default_action_registry
from framework.logging.runtime_logger import FailureContext
from framework.page_objects.base_page import BasePage
from framework.parser import get_parser
from framework.selenium.wrapper import Locator
from framework.selenium import (
    AssertionMismatch,
    BrowserSessionError,
    LocatorError,
    WaitTimeoutError,
)

from .execution_control import select_cases
from .models import (
    CaseExecutionResult,
    FailureType,
    StepExecutionResult,
    SuiteExecutionResult,
)


PageFactory = Callable[[], BasePage]
VARIABLE_PATTERN = re.compile(r"\$\{([^{}]+)\}")
LOCATOR_ACTIONS = {
    "click",
    "type",
    "clear",
    "assert_text",
    "wait_visible",
    "wait_not_visible",
    "wait_gone",
    "wait_clickable",
    "wait_text",
    "assert_element_visible",
    "assert_element_contains",
    "select",
    "hover",
    "upload_file",
}


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
    action_registry: ActionRegistry = field(default_factory=default_action_registry)

    def run_file(
        self,
        dsl_path: str | Path,
        include_tag_expr: str | None = None,
        exclude_tag_expr: str | None = None,
        run_empty_suite: bool = False,
        allowed_case_names: set[str] | None = None,
        workers: int = 1,
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
        )

    def run_suite(
        self,
        suite: SuiteSpec,
        include_tag_expr: str | None = None,
        exclude_tag_expr: str | None = None,
        run_empty_suite: bool = False,
        allowed_case_names: set[str] | None = None,
        workers: int = 1,
    ) -> SuiteExecutionResult:
        selected_cases = select_cases(
            suite.cases,
            include_expr=include_tag_expr,
            exclude_expr=exclude_tag_expr,
            allowed_case_names=allowed_case_names,
        )
        if not selected_cases and not run_empty_suite:
            raise ValueError("Suite contains no runnable cases after filtering.")

        case_results: list[CaseExecutionResult] = []
        passed = 0
        failed = 0
        variables = dict(suite.variables)
        suite_setup_outcome = self._run_steps_block(
            page=self.page_factory(),
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
                        )
                    )
                failed = len(selected_cases)
            else:
                if workers <= 1 or len(selected_cases) <= 1:
                    for case in selected_cases:
                        result = self._run_case(suite, case)
                        case_results.append(result)
                else:
                    ordered_results: list[CaseExecutionResult | None] = [None] * len(
                        selected_cases
                    )
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        future_to_index = {
                            executor.submit(self._run_case, suite, case): index
                            for index, case in enumerate(selected_cases)
                        }
                        for future in as_completed(future_to_index):
                            ordered_results[future_to_index[future]] = future.result()
                    if any(result is None for result in ordered_results):
                        raise RuntimeError("Missing case execution result in parallel mode.")
                    case_results = [result for result in ordered_results if result is not None]
                passed = sum(1 for result in case_results if result.passed)
                failed = len(case_results) - passed
        finally:
            suite_teardown_outcome = self._run_steps_block(
                page=self.page_factory(),
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

        return SuiteExecutionResult(
            name=suite.name,
            total_cases=len(selected_cases),
            passed_cases=passed,
            failed_cases=failed,
            case_results=case_results,
            suite_teardown_failed=suite_teardown_outcome.failed,
            suite_teardown_error_message=suite_teardown_error_message,
            suite_teardown_failure_type=suite_teardown_outcome.failure_type,
        )

    def _run_case(self, suite: SuiteSpec, case: CaseSpec) -> CaseExecutionResult:
        max_retries = self._normalize_retry(case.retry)
        step_results: list[StepExecutionResult] = []
        if self.logger:
            self.logger.info(f"case_start name={case.name}")

        for attempt in range(max_retries + 1):
            page = self.page_factory()
            variables = dict(suite.variables)
            variables.update(case.variables)
            attempt_start = len(step_results)
            attempt_outcome = self._run_case_attempt(
                page=page,
                suite=suite,
                case=case,
                variables=variables,
                step_results=step_results,
                case_attempt=attempt + 1,
                case_max_retries=max_retries,
            )
            if not attempt_outcome.failed:
                return CaseExecutionResult(name=case.name, passed=True, step_results=step_results)
            if attempt < max_retries:
                del step_results[attempt_start:]
                if self.logger and hasattr(self.logger, "info"):
                    self.logger.info(
                        f"case_retry name={case.name} attempt={attempt + 1} "
                        f"max_retries={max_retries}"
                    )
                continue

            case_error_message = self._format_case_error(
                attempt_outcome.error_message,
                attempt_outcome.call_chain,
            )
            self._log_case_failure(
                page=page,
                case=case,
                outcome=attempt_outcome,
            )
            return CaseExecutionResult(
                name=case.name,
                passed=False,
                step_results=step_results,
                error_message=case_error_message,
                failure_type=attempt_outcome.failure_type,
            )

        return CaseExecutionResult(
            name=case.name,
            passed=False,
            step_results=step_results,
            error_message="Case execution failed",
            failure_type="unknown",
        )

    def _run_case_attempt(
        self,
        page: BasePage,
        suite: SuiteSpec,
        case: CaseSpec,
        variables: dict[str, str],
        step_results: list[StepExecutionResult],
        case_attempt: int,
        case_max_retries: int,
    ) -> _StepSequenceOutcome:
        setup_outcome = self._run_steps_block(
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
        if setup_outcome.fatal:
            teardown_outcome = self._run_steps_block(
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
            return self._merge_step_outcomes(setup_outcome, teardown_outcome)

        steps_outcome = self._run_steps_block(
            page=page,
            case_name=case.name,
            steps=case.steps,
            variables=variables,
            keywords=suite.keywords,
            step_results=step_results,
            case_continue_on_failure=case.continue_on_failure,
            case_attempt=case_attempt,
            case_max_retries=case_max_retries,
        )
        teardown_outcome = self._run_steps_block(
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
        return self._merge_step_outcomes(setup_outcome, steps_outcome, teardown_outcome)

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
        page: BasePage,
        case_name: str,
        steps: list[StepSpec],
        variables: dict[str, str],
        keywords: dict[str, list[StepSpec]],
        step_results: list[StepExecutionResult],
        case_continue_on_failure: bool,
        case_attempt: int,
        case_max_retries: int,
    ) -> _StepSequenceOutcome:
        first_failure: _StepExecutionError | None = None
        fatal_failure = False
        for step in steps:
            failure = self._execute_step_with_retry(
                page=page,
                case_name=case_name,
                step=step,
                variables=variables,
                keywords=keywords,
                step_results=step_results,
                call_chain=[],
                case_continue_on_failure=case_continue_on_failure,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
            )
            if failure is None:
                continue
            if first_failure is None:
                first_failure = failure
            if not self._should_continue_on_failure(step, case_continue_on_failure):
                fatal_failure = True
                break

        if first_failure is None:
            return _StepSequenceOutcome()
        return _StepSequenceOutcome(
            failed=True,
            fatal=fatal_failure,
            error_message=str(first_failure),
            failure_type=first_failure.failure_type,
            step=first_failure.step,
            call_chain=list(first_failure.call_chain),
            screenshot_path=first_failure.screenshot_path,
        )

    def _execute_step_with_retry(
        self,
        page: BasePage,
        case_name: str,
        step: StepSpec,
        variables: dict[str, str],
        keywords: dict[str, list[StepSpec]],
        step_results: list[StepExecutionResult],
        call_chain: list[str],
        case_continue_on_failure: bool,
        case_attempt: int,
        case_max_retries: int,
    ) -> _StepExecutionError | None:
        max_retries = self._normalize_retry(step.retry)
        retry_trace: list[dict[str, int | str]] = []
        for attempt in range(max_retries + 1):
            attempt_start = len(step_results)
            try:
                self._execute_step(
                    page=page,
                    case_name=case_name,
                    step=step,
                    variables=variables,
                    keywords=keywords,
                    step_results=step_results,
                    call_chain=call_chain,
                    case_continue_on_failure=case_continue_on_failure,
                    step_attempt=attempt + 1,
                    step_max_retries=max_retries,
                    case_attempt=case_attempt,
                    case_max_retries=case_max_retries,
                    retry_trace=retry_trace,
                )
                retry_trace.append({"attempt": attempt + 1, "status": "passed"})
                self._update_latest_step_retry_trace(step_results, retry_trace)
                return None
            except _StepExecutionError as exc:
                retry_trace.append(
                    {
                        "attempt": attempt + 1,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                self._update_latest_step_retry_trace(step_results, retry_trace)
                if attempt < max_retries:
                    del step_results[attempt_start:]
                    continue
                return exc
        return None

    def _execute_step(
        self,
        page: BasePage,
        case_name: str,
        step: StepSpec,
        variables: dict[str, str],
        keywords: dict[str, list[StepSpec]],
        step_results: list[StepExecutionResult],
        call_chain: list[str],
        case_continue_on_failure: bool,
        step_attempt: int,
        step_max_retries: int,
        case_attempt: int,
        case_max_retries: int,
        retry_trace: list[dict[str, int | str]],
    ) -> None:
        started_at = time.perf_counter()
        try:
            resolved_step = self._resolve_step_variables(step, variables)
        except ValueError as exc:
            self._record_step_result(
                page=page,
                case_name=case_name,
                step_results=step_results,
                step=step,
                passed=False,
                error_message=str(exc),
                call_chain=call_chain,
                failure_type="action",
                duration_ms=self._elapsed_ms(started_at),
                step_attempt=step_attempt,
                step_max_retries=step_max_retries,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
                retry_trace=retry_trace,
            )
            screenshot_path = step_results[-1].screenshot_path if step_results else None
            raise _StepExecutionError(
                str(exc),
                step,
                list(call_chain),
                "action",
                screenshot_path=screenshot_path,
            ) from exc

        action = resolved_step.action.lower()
        if action == "call":
            self._execute_keyword(
                page=page,
                case_name=case_name,
                step=resolved_step,
                variables=variables,
                keywords=keywords,
                step_results=step_results,
                call_chain=call_chain,
                case_continue_on_failure=case_continue_on_failure,
                started_at=started_at,
                step_attempt=step_attempt,
                step_max_retries=step_max_retries,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
                retry_trace=retry_trace,
            )
            return

        try:
            self._run_step(page, resolved_step)
        except Exception as exc:
            failure_type = self._classify_failure(exc, resolved_step)
            self._record_step_result(
                page=page,
                case_name=case_name,
                step_results=step_results,
                step=resolved_step,
                passed=False,
                error_message=str(exc),
                call_chain=call_chain,
                failure_type=failure_type,
                duration_ms=self._elapsed_ms(started_at),
                step_attempt=step_attempt,
                step_max_retries=step_max_retries,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
                retry_trace=retry_trace,
            )
            screenshot_path = step_results[-1].screenshot_path if step_results else None
            raise _StepExecutionError(
                str(exc),
                resolved_step,
                list(call_chain),
                failure_type,
                screenshot_path=screenshot_path,
            ) from exc

        self._record_step_result(
            page=page,
            case_name=case_name,
            step_results=step_results,
            step=resolved_step,
            passed=True,
            error_message=None,
            call_chain=call_chain,
            failure_type=None,
            duration_ms=self._elapsed_ms(started_at),
            step_attempt=step_attempt,
            step_max_retries=step_max_retries,
            case_attempt=case_attempt,
            case_max_retries=case_max_retries,
            retry_trace=retry_trace,
        )

    def _execute_keyword(
        self,
        page: BasePage,
        case_name: str,
        step: StepSpec,
        variables: dict[str, str],
        keywords: dict[str, list[StepSpec]],
        step_results: list[StepExecutionResult],
        call_chain: list[str],
        case_continue_on_failure: bool,
        started_at: float,
        step_attempt: int,
        step_max_retries: int,
        case_attempt: int,
        case_max_retries: int,
        retry_trace: list[dict[str, int | str]],
    ) -> None:
        keyword_name = step.target
        if keyword_name not in keywords:
            message = f"Keyword '{keyword_name}' is not defined."
            self._record_step_result(
                page=page,
                case_name=case_name,
                step_results=step_results,
                step=step,
                passed=False,
                error_message=message,
                call_chain=call_chain,
                failure_type="action",
                duration_ms=self._elapsed_ms(started_at),
                step_attempt=step_attempt,
                step_max_retries=step_max_retries,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
                retry_trace=retry_trace,
            )
            screenshot_path = step_results[-1].screenshot_path if step_results else None
            raise _StepExecutionError(
                message,
                step,
                list(call_chain),
                "action",
                screenshot_path=screenshot_path,
            )

        if keyword_name in call_chain:
            cycle = [*call_chain, keyword_name]
            message = f"Recursive keyword call detected: {' -> '.join(cycle)}"
            self._record_step_result(
                page=page,
                case_name=case_name,
                step_results=step_results,
                step=step,
                passed=False,
                error_message=message,
                call_chain=call_chain,
                failure_type="action",
                duration_ms=self._elapsed_ms(started_at),
                step_attempt=step_attempt,
                step_max_retries=step_max_retries,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
                retry_trace=retry_trace,
            )
            screenshot_path = step_results[-1].screenshot_path if step_results else None
            raise _StepExecutionError(
                message,
                step,
                cycle,
                "action",
                screenshot_path=screenshot_path,
            )

        nested_call_chain = [*call_chain, keyword_name]
        first_failure: _StepExecutionError | None = None
        for keyword_step in keywords[keyword_name]:
            failure = self._execute_step_with_retry(
                page=page,
                case_name=case_name,
                step=keyword_step,
                variables=variables,
                keywords=keywords,
                step_results=step_results,
                call_chain=nested_call_chain,
                case_continue_on_failure=case_continue_on_failure,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
            )
            if failure is None:
                continue
            if first_failure is None:
                first_failure = failure
            if not self._should_continue_on_failure(
                keyword_step,
                case_continue_on_failure,
            ):
                break

        if first_failure is not None:
            self._record_step_result(
                page=page,
                case_name=case_name,
                step_results=step_results,
                step=step,
                passed=False,
                error_message=str(first_failure),
                call_chain=call_chain,
                failure_type=first_failure.failure_type,
                duration_ms=self._elapsed_ms(started_at),
                step_attempt=step_attempt,
                step_max_retries=step_max_retries,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
                retry_trace=retry_trace,
            )
            raise _StepExecutionError(
                str(first_failure),
                first_failure.step,
                list(first_failure.call_chain),
                first_failure.failure_type,
                screenshot_path=first_failure.screenshot_path,
            )

        self._record_step_result(
            page=page,
            case_name=case_name,
            step_results=step_results,
            step=step,
            passed=True,
            error_message=None,
            call_chain=call_chain,
            failure_type=None,
            duration_ms=self._elapsed_ms(started_at),
            step_attempt=step_attempt,
            step_max_retries=step_max_retries,
            case_attempt=case_attempt,
            case_max_retries=case_max_retries,
            retry_trace=retry_trace,
        )

    def _record_step_result(
        self,
        page: BasePage,
        case_name: str,
        step_results: list[StepExecutionResult],
        step: StepSpec,
        passed: bool,
        error_message: str | None,
        call_chain: list[str],
        failure_type: FailureType | None,
        duration_ms: int,
        step_attempt: int,
        step_max_retries: int,
        case_attempt: int,
        case_max_retries: int,
        retry_trace: list[dict[str, int | str]],
    ) -> None:
        if self.logger and passed:
            self.logger.info(
                f"step_pass case={case_name} action={step.action} "
                f"locator={step.target} call_chain={' > '.join(call_chain) if call_chain else '-'}"
            )
        step_results.append(
            StepExecutionResult(
                action=step.action,
                target=step.target,
                passed=passed,
                error_message=error_message,
                call_chain=list(call_chain),
                failure_type=failure_type,
                duration_ms=duration_ms,
                retry_attempt=step_attempt,
                retry_max_retries=step_max_retries,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
                retry_trace=list(retry_trace),
                resolved_locator=self._resolve_locator(step),
                current_url=self._resolve_current_url(page),
                screenshot_path=(
                    self._capture_step_screenshot(page, case_name, step)
                    if not passed
                    else None
                ),
                page_source_path=(
                    self._capture_page_source(page, case_name, step)
                    if not passed
                    else None
                ),
                browser_alias=self._resolve_browser_alias(page),
                page_title=self._resolve_page_title(page),
            )
        )

    def _update_latest_step_retry_trace(
        self,
        step_results: list[StepExecutionResult],
        retry_trace: list[dict[str, int | str]],
    ) -> None:
        if not step_results:
            return
        step_results[-1] = replace(step_results[-1], retry_trace=list(retry_trace))

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))

    def _resolve_locator(self, step: StepSpec) -> dict[str, str] | None:
        action = step.action.lower()
        if action not in LOCATOR_ACTIONS and not (
            action == "switch_frame" and step.target is not None and "=" in step.target
        ):
            return None
        if step.target is None:
            return None
        locator = Locator.parse(step.target)
        return {"raw": step.target, "by": locator.by, "value": locator.value}

    def _resolve_step_variables(self, step: StepSpec, variables: dict[str, str]) -> StepSpec:
        return StepSpec(
            action=self._substitute_variables(step.action, variables, "action"),
            target=(
                self._substitute_variables(step.target, variables, "target")
                if step.target is not None
                else None
            ),
            value=(
                self._substitute_variables(step.value, variables, "value")
                if step.value is not None
                else None
            ),
            timeout=(
                self._substitute_variables(str(step.timeout), variables, "timeout")
                if step.timeout is not None
                else None
            ),
            retry=step.retry,
            continue_on_failure=step.continue_on_failure,
        )

    def _substitute_variables(
        self,
        raw_value: str,
        variables: dict[str, str],
        field: str,
    ) -> str:
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name not in variables:
                raise ValueError(f"Undefined variable '{var_name}' in step {field}")
            return variables[var_name]

        return VARIABLE_PATTERN.sub(_replace, raw_value)

    def _capture_failure_screenshot(
        self,
        page: BasePage,
        case: CaseSpec,
        step: StepSpec,
    ) -> str:
        screenshot = self._build_artifact_path(self.screenshot_dir, case.name, step, ".png")
        page.screenshot(screenshot)
        return screenshot

    def _capture_step_screenshot(
        self,
        page: BasePage,
        case_name: str,
        step: StepSpec,
    ) -> str | None:
        screenshot = self._build_artifact_path(self.screenshot_dir, case_name, step, ".png")
        try:
            page.screenshot(screenshot)
        except Exception as exc:
            if self.logger and hasattr(self.logger, "error"):
                self.logger.error(
                    f"screenshot_capture_failed case={case_name} "
                    f"action={step.action} error={exc}"
                )
            return None
        return screenshot

    def _capture_page_source(
        self,
        page: BasePage,
        case_name: str,
        step: StepSpec,
    ) -> str | None:
        driver = self._resolve_driver(page)
        page_source = getattr(driver, "page_source", None)
        if not isinstance(page_source, str):
            return None
        path = Path(self._build_artifact_path(self.page_source_dir, case_name, step, ".html"))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page_source, encoding="utf-8", errors="replace")
        except Exception as exc:
            if self.logger and hasattr(self.logger, "error"):
                self.logger.error(
                    f"page_source_capture_failed case={case_name} "
                    f"action={step.action} error={exc}"
                )
            return None
        return str(path)

    def _build_artifact_path(
        self,
        directory: str,
        case_name: str,
        step: StepSpec,
        extension: str,
    ) -> str:
        safe_case = self._safe_artifact_name(case_name)
        safe_action = self._safe_artifact_name(step.action)
        return str(Path(directory) / f"{safe_case}_{safe_action}_{uuid4().hex}{extension}")

    def _safe_artifact_name(self, value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip().lower())
        return normalized.strip("_") or "artifact"

    def _resolve_current_url(self, page: BasePage) -> str:
        driver = self._resolve_driver(page)
        current_url = getattr(driver, "current_url", None)
        return current_url if current_url else "unknown"

    def _resolve_page_title(self, page: BasePage) -> str | None:
        title = getattr(self._resolve_driver(page), "title", None)
        return title if isinstance(title, str) else None

    def _resolve_browser_alias(self, page: BasePage) -> str | None:
        actions = getattr(page, "actions", None)
        alias = getattr(actions, "current_alias", None)
        return alias if isinstance(alias, str) else None

    def _resolve_driver(self, page: BasePage):
        actions = getattr(page, "actions", None)
        return getattr(actions, "driver", None)

    def _parse_wait_text_value(self, raw_value: str) -> tuple[str, int]:
        timeout_suffix = "|timeout="
        if timeout_suffix not in raw_value:
            return raw_value, 10

        expected, timeout_raw = raw_value.rsplit(timeout_suffix, 1)
        try:
            timeout = int(timeout_raw)
        except ValueError as exc:
            raise ValueError(
                "Action 'wait_text' timeout must be a positive integer when '|timeout=' is provided."
            ) from exc
        if timeout <= 0:
            raise ValueError(
                "Action 'wait_text' timeout must be a positive integer when '|timeout=' is provided."
            )
        return expected, timeout

    def _run_step(self, page: BasePage, step: StepSpec) -> None:
        action = step.action.lower()
        if action == "open":
            page.open(step.target)
            return
        if action == "click":
            page.click(step.target)
            return
        if action == "type":
            if step.value is None:
                raise ValueError("Action 'type' requires a value.")
            page.type(step.target, step.value)
            return
        if action == "assert_text":
            if step.value is None:
                raise ValueError("Action 'assert_text' requires a value.")
            page.assert_text(step.target, step.value)
            return
        if action == "wait_visible":
            timeout = int(step.value) if step.value else 10
            page.wait_visible(step.target, timeout=timeout)
            return
        if action == "wait_clickable":
            timeout = int(step.value) if step.value else 10
            page.wait_clickable(step.target, timeout=timeout)
            return
        if action == "wait_text":
            if step.value is None:
                raise ValueError("Action 'wait_text' requires a value.")
            expected_text, timeout = self._parse_wait_text_value(step.value)
            page.wait_text(step.target, expected_text, timeout=timeout)
            return
        if action == "wait_url_contains":
            timeout = int(step.value) if step.value else 10
            page.wait_url_contains(step.target, timeout=timeout)
            return
        if action == "assert_element_visible":
            timeout = int(step.value) if step.value else 10
            page.assert_element_visible(step.target, timeout=timeout)
            return
        if action == "assert_element_contains":
            if step.value is None:
                raise ValueError("Action 'assert_element_contains' requires a value.")
            page.assert_element_contains(step.target, step.value)
            return
        if action == "select":
            if step.value is None:
                raise ValueError("Action 'select' requires a value.")
            page.select(step.target, step.value)
            return
        if action == "hover":
            page.hover(step.target)
            return
        if action == "switch_frame":
            page.switch_frame(step.target)
            return
        if action == "switch_window":
            page.switch_window(step.target)
            return
        if action == "accept_alert":
            timeout = int(step.value) if step.value else 10
            page.accept_alert(timeout=timeout)
            return
        if action == "upload_file":
            if step.value is None:
                raise ValueError("Action 'upload_file' requires a value.")
            page.upload_file(step.target, step.value)
            return
        if action == "screenshot":
            path = step.value or step.target
            page.screenshot(path)
            return
        raise ValueError(f"Unsupported action: '{step.action}'")

    def _should_continue_on_failure(
        self,
        step: StepSpec,
        case_continue_on_failure: bool,
    ) -> bool:
        return step.continue_on_failure or case_continue_on_failure

    def _normalize_retry(self, retry: int | None) -> int:
        if isinstance(retry, int) and retry > 0:
            return retry
        return 0

    def _classify_failure(self, exc: Exception, step: StepSpec) -> FailureType:
        action = step.action.lower()
        if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
            return "timeout"
        if isinstance(exc, AssertionError) or action.startswith("assert"):
            return "assertion"
        if isinstance(exc, ValueError):
            return "action"
        return "unknown"

    def _format_case_error(self, message: str | None, call_chain: list[str]) -> str:
        resolved_message = message or "Case failed."
        if call_chain:
            return f"{resolved_message} (call_chain: {' > '.join(call_chain)})"
        return resolved_message

    def _log_case_failure(
        self,
        page: BasePage,
        case: CaseSpec,
        outcome: _StepSequenceOutcome,
    ) -> None:
        if not self.logger or outcome.step is None:
            return
        screenshot = "unavailable"
        try:
            screenshot = self._capture_failure_screenshot(page, case, outcome.step)
        except Exception as screenshot_error:
            if hasattr(self.logger, "error"):
                self.logger.error(
                    f"screenshot_capture_failed case={case.name} "
                    f"action={outcome.step.action} error={screenshot_error}"
                )
        error_message = outcome.error_message or "Case failed."
        if outcome.call_chain:
            error_message = f"{error_message} call_chain={' > '.join(outcome.call_chain)}"
        failure_context = FailureContext(
            url=self._resolve_current_url(page),
            locator=outcome.step.target,
            screenshot_path=screenshot,
            error=error_message,
        )
        self.logger.error(failure_context.to_log_message())
