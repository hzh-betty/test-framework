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
                    CaseExecutionResult(
                        name="CasePass",
                        passed=True,
                        step_results=[StepExecutionResult(action="open", target="url", passed=True)],
                    ),
                    CaseExecutionResult(
                        name="CaseFail",
                        passed=False,
                        step_results=[
                            StepExecutionResult(
                                action="assert_text",
                                target="id=title",
                                passed=False,
                                error_message="mismatch",
                            )
                        ],
                        error_message="mismatch",
                    ),
                ],
            )

            summary_file = reporter.write_suite_result(suite_result)

            self.assertTrue(summary_file.exists())
            payload = json.loads(summary_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["suite"], "SmokeSuite")
            self.assertEqual(payload["failed_cases"], 1)
            result_files = list((Path(tmpdir) / "allure-results").glob("*-result.json"))
            self.assertEqual(len(result_files), 2)

    def test_generate_html_report_uses_allure_cli(self):
        calls: list[list[str]] = []

        def fake_runner(cmd: list[str]) -> int:
            calls.append(cmd)
            return 0

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AllureReporter(
                results_dir=Path(tmpdir) / "allure-results",
                command_runner=fake_runner,
            )

            generated = reporter.generate_html_report(output_dir=Path(tmpdir) / "allure-report")

            self.assertTrue(generated)
            self.assertEqual(calls[0][:3], ["allure", "generate", str(reporter.results_dir)])

    def test_generate_html_report_returns_false_when_command_runner_raises(self):
        def failing_runner(_cmd: list[str]) -> int:
            raise FileNotFoundError("allure command not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AllureReporter(
                results_dir=Path(tmpdir) / "allure-results",
                command_runner=failing_runner,
            )
            generated = reporter.generate_html_report(output_dir=Path(tmpdir) / "allure-report")

        self.assertFalse(generated)


if __name__ == "__main__":
    unittest.main()
