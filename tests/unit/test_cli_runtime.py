import tempfile
import unittest
from pathlib import Path

from framework.executor.models import SuiteExecutionResult
from framework.cli.main import RuntimeDependencies, main


class FakeDriverManager:
    def __init__(self):
        self.created = False
        self.quitted = False
        self.driver = object()

    def create_driver(self, _config):
        self.created = True
        return self.driver

    def quit_driver(self, _driver):
        self.quitted = True


class FakeExecutor:
    def __init__(self, suite_result: SuiteExecutionResult):
        self.suite_result = suite_result
        self.run_file_calls = []

    def run_file(self, dsl_path: str):
        self.run_file_calls.append(dsl_path)
        return self.suite_result


class FakeReporter:
    def __init__(self, generated: bool = True):
        self.written = False
        self.generated = False
        self._generated_value = generated

    def write_suite_result(self, _result, context=None):
        self.written = True
        return Path("artifacts/allure-results/executor-summary.json")

    def write_environment_properties(self, _context):
        return Path("artifacts/allure-results/environment.properties")

    def generate_html_report(self, output_dir):
        self.generated = True
        return self._generated_value


class FakeNotifier:
    def __init__(self):
        self.sent = False

    def send(self, **_kwargs):
        self.sent = True


class FakeLogger:
    def __init__(self):
        self.info_messages = []
        self.error_messages = []

    def info(self, message: str):
        self.info_messages.append(message)

    def error(self, message: str):
        self.error_messages.append(message)


class TestCliRuntime(unittest.TestCase):
    def test_main_passes_report_context_to_reporter(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        executor = FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                case_results=[],
            )
        )
        captured = {}

        class ReporterSpy(FakeReporter):
            def write_suite_result(self, result, context=None):
                captured["browser"] = getattr(context, "browser", None)
                return super().write_suite_result(result, context=context)

        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda _driver: object(),
            executor_factory=lambda _actions, _logger: executor,
            reporter_factory=lambda _results_dir: ReporterSpy(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_file = Path(tmpdir) / "case.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite"><case name="Login"><step action="open" target="https://example.test" /></case></suite>
""",
                encoding="utf-8",
            )
            rc = main([str(xml_file), "--allure", "--browser", "chrome"], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertEqual(captured["browser"], "chrome")

    def test_main_executes_pipeline_and_returns_zero_when_all_passed(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        executor = FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                case_results=[],
            )
        )
        reporter = FakeReporter()

        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda _driver: object(),
            executor_factory=lambda _actions, _logger: executor,
            reporter_factory=lambda _results_dir: reporter,
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_file = Path(tmpdir) / "case.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite"><case name="Login"><step action="open" target="https://example.test" /></case></suite>
""",
                encoding="utf-8",
            )
            rc = main([str(xml_file), "--allure"], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertTrue(driver_manager.created)
        self.assertTrue(driver_manager.quitted)
        self.assertTrue(reporter.written)
        self.assertTrue(reporter.generated)

    def test_main_returns_nonzero_when_case_failed(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        executor = FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=0,
                failed_cases=1,
                case_results=[],
            )
        )
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda _driver: object(),
            executor_factory=lambda _actions, _logger: executor,
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_file = Path(tmpdir) / "case.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite"><case name="Login"><step action="open" target="https://example.test" /></case></suite>
""",
                encoding="utf-8",
            )
            rc = main([str(xml_file)], dependencies=deps)

        self.assertEqual(rc, 1)

    def test_main_logs_error_when_allure_report_generation_fails(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        executor = FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                case_results=[],
            )
        )
        reporter = FakeReporter(generated=False)
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda _driver: object(),
            executor_factory=lambda _actions, _logger: executor,
            reporter_factory=lambda _results_dir: reporter,
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_file = Path(tmpdir) / "case.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite"><case name="Login"><step action="open" target="https://example.test" /></case></suite>
""",
                encoding="utf-8",
            )
            rc = main([str(xml_file), "--allure"], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertIn("Allure report generation failed", logger.error_messages[0])


if __name__ == "__main__":
    unittest.main()
