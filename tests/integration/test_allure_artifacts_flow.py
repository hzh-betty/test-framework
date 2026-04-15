import json
import tempfile
import unittest
from pathlib import Path

from framework.cli.main import RuntimeDependencies, main
from framework.executor.models import CaseExecutionResult, StepExecutionResult, SuiteExecutionResult
from framework.reporting import AllureReporter


class FakeDriverManager:
    def __init__(self):
        self.driver = object()

    def create_driver(self, _config):
        return self.driver

    def quit_driver(self, _driver):
        return None


class FakeExecutor:
    def __init__(self, suite_result: SuiteExecutionResult):
        self.suite_result = suite_result

    def run_file(self, _dsl_path: str):
        return self.suite_result


class FakeNotifier:
    def send(self, **_kwargs):
        return None


class FakeLogger:
    def info(self, _message: str):
        return None

    def error(self, _message: str):
        return None


class TestAllureArtifactsFlow(unittest.TestCase):
    def test_allure_artifacts_flow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            results_dir = tmp / "allure-results"
            report_dir = tmp / "allure-report"
            xml_file = tmp / "case.xml"
            xml_file.write_text(
                "<suite name='Smoke'><case name='Login'><step action='open' target='https://example.test' /></case></suite>",
                encoding="utf-8",
            )
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
                            )
                        ],
                        error_message="mismatch",
                    )
                ],
            )

            deps = RuntimeDependencies(
                driver_manager_factory=lambda: FakeDriverManager(),
                actions_factory=lambda _driver: object(),
                executor_factory=lambda _actions, _logger: FakeExecutor(suite_result),
                reporter_factory=lambda _dir: AllureReporter(results_dir=results_dir),
                logger_factory=lambda _level, _file: FakeLogger(),
                email_notifier_factory=lambda _config: FakeNotifier(),
                dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
            )

            rc = main(
                [
                    str(xml_file),
                    "--allure",
                    "--allure-results-dir",
                    str(results_dir),
                    "--allure-report-dir",
                    str(report_dir),
                ],
                dependencies=deps,
            )

            self.assertEqual(rc, 1)
            self.assertTrue(any(results_dir.glob("*-result.json")))
            self.assertTrue((results_dir / "environment.properties").exists())
            self.assertTrue((results_dir / "executor-summary.json").exists())

            case_result_file = next(results_dir.glob("*-result.json"))
            payload = json.loads(case_result_file.read_text(encoding="utf-8"))
            attachment_names = {a["name"] for a in payload["attachments"]}
            self.assertIn("runtime.log", attachment_names)
            self.assertIn("dsl-snippet.xml", attachment_names)


if __name__ == "__main__":
    unittest.main()
