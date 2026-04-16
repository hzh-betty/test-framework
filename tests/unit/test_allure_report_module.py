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
                                failure_type="assertion",
                            )
                        ],
                        error_message="mismatch",
                        failure_type="assertion",
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

    def test_write_suite_result_contains_steps_and_attachments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AllureReporter(results_dir=Path(tmpdir) / "allure-results")
            suite_result = SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=0,
                failed_cases=1,
                case_results=[
                    CaseExecutionResult(
                        name="Login",
                        passed=False,
                        step_results=[
                            StepExecutionResult(
                                action="assert_text",
                                target="id=welcome",
                                passed=False,
                                error_message="mismatch",
                                failure_type="timeout",
                                duration_ms=128,
                                retry_attempt=2,
                                retry_max_retries=3,
                                case_attempt=1,
                                case_max_retries=0,
                                retry_trace=[
                                    {"attempt": 1, "status": "failed", "error": "timeout 1"},
                                    {"attempt": 2, "status": "failed", "error": "timeout 2"},
                                ],
                                resolved_locator={
                                    "raw": "id=welcome",
                                    "by": "id",
                                    "value": "welcome",
                                },
                                current_url="https://example.test/login",
                            )
                        ],
                        error_message="mismatch",
                        failure_type="timeout",
                    )
                ],
            )
            context = ReportContext(
                browser="chrome",
                headless=True,
                python_version="3.12.3",
                framework_version="0.1.0",
                runtime_log_path="artifacts/runtime.log",
                dsl_path="examples/cases/login.xml",
            )

            reporter.write_suite_result(suite_result, context=context)
            files = list((Path(tmpdir) / "allure-results").glob("*-result.json"))
            payload = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["steps"][0]["name"], "assert_text id=welcome")
            self.assertEqual(payload["steps"][0]["status"], "failed")
            self.assertEqual(payload["steps"][0]["statusDetails"]["failureType"], "timeout")
            self.assertEqual(
                payload["steps"][0]["statusDetails"]["diagnostics"]["duration_ms"],
                128,
            )
            self.assertEqual(
                payload["steps"][0]["statusDetails"]["diagnostics"]["current_url"],
                "https://example.test/login",
            )
            self.assertEqual(
                payload["steps"][0]["statusDetails"]["diagnostics"]["resolved_locator"],
                {"raw": "id=welcome", "by": "id", "value": "welcome"},
            )
            self.assertEqual(
                payload["steps"][0]["statusDetails"]["diagnostics"]["retry_trace"],
                [
                    {"attempt": 1, "status": "failed", "error": "timeout 1"},
                    {"attempt": 2, "status": "failed", "error": "timeout 2"},
                ],
            )
            parameters = {item["name"]: item["value"] for item in payload["steps"][0]["parameters"]}
            self.assertEqual(parameters["duration_ms"], "128")
            self.assertEqual(parameters["retry_attempt"], "2")
            self.assertEqual(parameters["retry_max_retries"], "3")
            self.assertEqual(parameters["locator_by"], "id")
            self.assertEqual(parameters["locator_value"], "welcome")
            self.assertEqual(parameters["current_url"], "https://example.test/login")
            self.assertEqual(payload["statusDetails"]["failureType"], "timeout")
            self.assertIn({"name": "failureType", "value": "timeout"}, payload["labels"])
            self.assertIn("attachments", payload)

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
