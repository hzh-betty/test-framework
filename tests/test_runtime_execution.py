from pathlib import Path

import pytest

from webtest_core.dsl import load_suite
from webtest_core.keywords import KeywordRegistry, keyword
from webtest_core.runtime import SuiteExecutor


class DemoKeywords:
    """Small keyword library used by tests to exercise the runtime without Selenium."""

    def __init__(self):
        self.calls: list[str] = []
        self.flaky_attempts = 0
        self.case_flaky_attempts = 0

    @keyword("Record")
    def record(self, value: str):
        self.calls.append(value)

    @keyword("Flaky")
    def flaky(self):
        self.flaky_attempts += 1
        if self.flaky_attempts == 1:
            raise AssertionError("try again")

    @keyword("Always Fail")
    def always_fail(self):
        raise AssertionError("expected failure")

    @keyword("Case Flaky")
    def case_flaky(self):
        self.case_flaky_attempts += 1
        if self.case_flaky_attempts == 1:
            raise AssertionError("case try again")


def test_executor_runs_setup_cases_teardown_retries_and_continue_on_failure(tmp_path: Path):
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
suite:
  name: RuntimeSuite
  setup:
    - keyword: Record
      args: [suite-setup]
  cases:
    - name: Retry Case
      tags: [smoke]
      steps:
        - keyword: Flaky
          retry: 1
        - keyword: Record
          args: [after-retry]
    - name: Continue Case
      tags: [smoke]
      continue_on_failure: true
      steps:
        - keyword: Always Fail
        - keyword: Record
          args: [after-failure]
  teardown:
    - keyword: Record
      args: [suite-teardown]
""",
        encoding="utf-8",
    )
    library = DemoKeywords()
    registry = KeywordRegistry.from_libraries([library])

    result = SuiteExecutor(registry=registry).run_suite(load_suite(suite_file))

    assert result.total_cases == 2
    assert result.passed_cases == 1
    assert result.failed_cases == 1
    assert library.flaky_attempts == 2
    assert library.calls == ["suite-setup", "after-retry", "after-failure", "suite-teardown"]
    assert result.case_results[0].step_results[0].retry_attempt == 2
    assert result.case_results[1].step_results[0].failure_type == "assertion"


def test_executor_filters_and_dry_run_validates_keywords_without_calling_them(tmp_path: Path):
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
suite:
  name: DryRunSuite
  cases:
    - name: Selected
      module: auth
      tags: [smoke]
      steps:
        - keyword: Record
          args: [selected]
    - name: Skipped
      module: billing
      tags: [regression]
      steps:
        - keyword: Record
          args: [skipped]
""",
        encoding="utf-8",
    )
    library = DemoKeywords()
    registry = KeywordRegistry.from_libraries([library])

    result = SuiteExecutor(registry=registry, dry_run=True).run_suite(
        load_suite(suite_file),
        include_tag_expr="smoke",
        modules={"auth"},
        workers=2,
    )

    assert result.total_cases == 1
    assert result.case_results[0].name == "Selected"
    assert result.case_results[0].step_results[0].dry_run is True
    assert library.calls == []


def test_executor_reports_unknown_keywords_as_validation_errors(tmp_path: Path):
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
suite:
  name: UnknownSuite
  cases:
    - name: Broken
      steps:
        - keyword: Does Not Exist
""",
        encoding="utf-8",
    )

    result = SuiteExecutor(registry=KeywordRegistry()).run_suite(load_suite(suite_file))

    assert result.failed_cases == 1
    assert result.case_results[0].failure_type == "validation"
    assert "Does Not Exist" in result.case_results[0].error_message


def test_executor_records_diagnostics_and_retries_whole_case(tmp_path: Path):
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
suite:
  name: DiagnosticsSuite
  cases:
    - name: Case Retry
      retry: 1
      steps:
        - keyword: Case Flaky
        - keyword: Record
          args: [after-case-retry]
""",
        encoding="utf-8",
    )
    library = DemoKeywords()
    registry = KeywordRegistry.from_libraries([library])

    result = SuiteExecutor(registry=registry).run_suite(load_suite(suite_file))

    assert result.passed_cases == 1
    case = result.case_results[0]
    assert case.passed is True
    assert case.step_results[0].case_attempt == 2
    assert case.step_results[0].case_max_retries == 1
    assert case.step_results[0].duration_ms >= 0
    assert case.step_results[0].retry_trace[0]["status"] == "failed"
    assert library.case_flaky_attempts == 2
