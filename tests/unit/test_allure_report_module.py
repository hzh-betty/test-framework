import json
import tempfile
import unittest
from pathlib import Path

from framework.executor.models import CaseExecutionResult, StepExecutionResult, SuiteExecutionResult
from framework.reporting.allure_reporter import AllureReporter, ReportContext


class TestAllureReportModule(unittest.TestCase):
    def test_write_environment_properties_contains_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AllureReporter(results_dir=Path(tmpdir) / "allure-results")
            context = ReportContext(
                browser="chrome",
                headless=True,
                python_version="3.12.3",
                framework_version="0.1.0",
                runtime_log_path="artifacts/runtime.log",
                dsl_path="examples/cases/login.xml",
            )
            env_path = reporter.write_environment_properties(context)
            content = env_path.read_text(encoding="utf-8")
            self.assertIn("browser=chrome", content)
            self.assertIn("headless=true", content)
            self.assertIn("python=3.12.3", content)
            self.assertIn("version=0.1.0", content)

    def test_write_suite_result_creates_summary_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AllureReporter(results_dir=Path(tmpdir) / "allure-results")
            suite_result = SuiteExecutionResult(
                name="SmokeSuite",
                total_cases=2,
                passed_cases=1,
                failed_cases=1,
                case_results=[
