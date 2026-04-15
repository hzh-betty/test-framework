from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.logging.runtime_logger import FailureContext
from framework.page_objects.base_page import BasePage
from framework.parser import get_parser

from .models import CaseExecutionResult, StepExecutionResult, SuiteExecutionResult


PageFactory = Callable[[], BasePage]


@dataclass
class Executor:
    page_factory: PageFactory
    logger: object | None = None
    screenshot_dir: str = "artifacts/screenshots"

    def run_file(self, dsl_path: str | Path) -> SuiteExecutionResult:
        parser = get_parser(dsl_path)
        suite = parser.parse(dsl_path)
        return self.run_suite(suite)

    def run_suite(self, suite: SuiteSpec) -> SuiteExecutionResult:
        case_results: list[CaseExecutionResult] = []
        passed = 0
        failed = 0

        for case in suite.cases:
            result = self._run_case(case)
            case_results.append(result)
            if result.passed:
                passed += 1
            else:
                failed += 1

        return SuiteExecutionResult(
            name=suite.name,
            total_cases=len(suite.cases),
            passed_cases=passed,
            failed_cases=failed,
            case_results=case_results,
        )

    def _run_case(self, case: CaseSpec) -> CaseExecutionResult:
        page = self.page_factory()
        step_results: list[StepExecutionResult] = []
        if self.logger:
            self.logger.info(f"case_start name={case.name}")

        for step in case.steps:
            try:
                self._run_step(page, step)
                if self.logger:
                    self.logger.info(
                        f"step_pass case={case.name} action={step.action} locator={step.target}"
                    )
                step_results.append(
                    StepExecutionResult(
                        action=step.action,
                        target=step.target,
                        passed=True,
                    )
                )
            except Exception as exc:
                message = str(exc)
                if self.logger:
                    screenshot = "unavailable"
                    try:
                        screenshot = self._capture_failure_screenshot(page, case, step)
                    except Exception as screenshot_error:
                        if hasattr(self.logger, "error"):
                            self.logger.error(
                                f"screenshot_capture_failed case={case.name} "
                                f"action={step.action} error={screenshot_error}"
                            )
                    failure_context = FailureContext(
                        url=self._resolve_current_url(page),
                        locator=step.target,
                        screenshot_path=screenshot,
                        error=message,
                    )
                    self.logger.error(failure_context.to_log_message())
                step_results.append(
                    StepExecutionResult(
                        action=step.action,
                        target=step.target,
                        passed=False,
                        error_message=message,
                    )
                )
                return CaseExecutionResult(
                    name=case.name,
                    passed=False,
                    step_results=step_results,
                    error_message=message,
                )

        return CaseExecutionResult(name=case.name, passed=True, step_results=step_results)

    def _capture_failure_screenshot(
        self,
        page: BasePage,
        case: CaseSpec,
        step: StepSpec,
    ) -> str:
        safe_case = case.name.strip().lower().replace(" ", "_")
        safe_action = step.action.strip().lower().replace(" ", "_")
        screenshot = f"{self.screenshot_dir}/{safe_case}_{safe_action}.png"
        page.screenshot(screenshot)
        return screenshot

    def _resolve_current_url(self, page: BasePage) -> str:
        actions = getattr(page, "actions", None)
        driver = getattr(actions, "driver", None)
        current_url = getattr(driver, "current_url", None)
        return current_url if current_url else "unknown"

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
        if action == "screenshot":
            path = step.value or step.target
            page.screenshot(path)
            return
        raise ValueError(f"Unsupported action: '{step.action}'")
