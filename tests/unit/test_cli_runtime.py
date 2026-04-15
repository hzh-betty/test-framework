import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from framework.executor.models import CaseExecutionResult, SuiteExecutionResult
from framework.reporting.case_results import write_case_results
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

    def run_file(self, dsl_path: str, **kwargs):
        self.run_file_calls.append((dsl_path, kwargs))
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
    def test_main_passes_execution_control_options_to_executor(self):
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
<suite name="SmokeSuite"><case name="Login" tags="smoke"><step action="open" target="https://example.test" /></case></suite>
""",
                encoding="utf-8",
            )
            rc = main(
                [
                    str(xml_file),
                    "--include-tag-expr",
                    "smoke",
                    "--exclude-tag-expr",
                    "flaky",
                    "--run-empty-suite",
                ],
                dependencies=deps,
            )

        self.assertEqual(rc, 0)
        self.assertEqual(
            executor.run_file_calls,
            [
                (
                    str(xml_file),
                    {
                        "include_tag_expr": "smoke",
                        "exclude_tag_expr": "flaky",
                        "run_empty_suite": True,
                        "allowed_case_names": None,
                    },
                )
            ],
        )


    def test_main_loads_rerunfailed_and_passes_allowed_case_names_to_executor(self):
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
            tmpdir_path = Path(tmpdir)
            xml_file = tmpdir_path / "case.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite"><case name="Login"><step action="open" target="https://example.test" /></case></suite>
""",
                encoding="utf-8",
            )
            rerun_file = tmpdir_path / "rerun.json"
            write_case_results(
                rerun_file,
                [
                    {"name": "Login", "passed": False},
                    {"name": "Checkout", "passed": True},
                ],
            )
            rc = main([str(xml_file), "--rerunfailed", str(rerun_file)], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertEqual(
            executor.run_file_calls,
            [
                (
                    str(xml_file),
                    {
                        "include_tag_expr": None,
                        "exclude_tag_expr": None,
                        "run_empty_suite": False,
                        "allowed_case_names": {"Login"},
                    },
                )
            ],
        )

    def test_main_writes_case_results_artifact(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        suite_result = SuiteExecutionResult(
            name="Smoke",
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            case_results=[
                CaseExecutionResult(name="Login", passed=True, step_results=[]),
            ],
        )
        executor = FakeExecutor(suite_result)
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
            with patch("framework.cli.main.write_case_results") as write_spy:
                rc = main([str(xml_file)], dependencies=deps)

        self.assertEqual(rc, 0)
        write_spy.assert_called_once_with(
            Path("artifacts/case-results.json"),
            [{"name": "Login", "passed": True, "step_results": [], "error_message": None}],
        )


    def test_main_combines_rerunfailed_with_tag_filters(self):
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
            tmpdir_path = Path(tmpdir)
            xml_file = tmpdir_path / "case.xml"
            xml_file.write_text(
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<suite name=\"SmokeSuite\"><case name=\"Login\" tags=\"smoke\"><step action=\"open\" target=\"https://example.test\" /></case></suite>
""",
                encoding="utf-8",
            )
            rerun_file = tmpdir_path / "rerun.json"
            write_case_results(
                rerun_file,
                [
                    {"name": "Login", "passed": False},
                    {"name": "Checkout", "passed": False},
                ],
            )
            rc = main(
                [
                    str(xml_file),
                    "--rerunfailed",
                    str(rerun_file),
                    "--include-tag-expr",
                    "smoke",
                    "--exclude-tag-expr",
                    "flaky",
                ],
                dependencies=deps,
            )

        self.assertEqual(rc, 0)
        self.assertEqual(
            executor.run_file_calls,
            [
                (
                    str(xml_file),
                    {
                        "include_tag_expr": "smoke",
                        "exclude_tag_expr": "flaky",
                        "run_empty_suite": False,
                        "allowed_case_names": {"Login", "Checkout"},
                    },
                )
            ],
        )

    def test_main_writes_empty_case_results_for_run_empty_suite(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda _driver: object(),
            executor_factory=lambda _actions, _logger: FakeExecutor(
                SuiteExecutionResult(
                    name="Smoke",
                    total_cases=1,
                    passed_cases=1,
                    failed_cases=0,
                    case_results=[],
                )
            ),
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_file = Path(tmpdir) / "case.xml"
            xml_file.write_text(
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<suite name=\"SmokeSuite\"><case name=\"Login\" tags=\"smoke\"><step action=\"open\" target=\"https://example.test\" /></case></suite>
""",
                encoding="utf-8",
            )
            with patch("framework.cli.main.write_case_results") as write_spy:
                rc = main(
                    [str(xml_file), "--include-tag-expr", "regression", "--run-empty-suite"],
                    dependencies=deps,
                )

        self.assertEqual(rc, 0)
        write_spy.assert_called_once_with(Path("artifacts/case-results.json"), [])

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

    def test_main_skips_driver_startup_for_empty_filtered_suite_when_allowed(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda _driver: object(),
            executor_factory=lambda _actions, _logger: FakeExecutor(
                SuiteExecutionResult(
                    name="Smoke",
                    total_cases=1,
                    passed_cases=1,
                    failed_cases=0,
                    case_results=[],
                )
            ),
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_file = Path(tmpdir) / "case.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite"><case name="Login" tags="smoke"><step action="open" target="https://example.test" /></case></suite>
""",
                encoding="utf-8",
            )
            rc = main(
                [str(xml_file), "--include-tag-expr", "regression", "--run-empty-suite"],
                dependencies=deps,
            )

        self.assertEqual(rc, 0)
        self.assertFalse(driver_manager.created)
        self.assertFalse(driver_manager.quitted)


if __name__ == "__main__":
    unittest.main()
