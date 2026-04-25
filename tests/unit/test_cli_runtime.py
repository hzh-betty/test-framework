from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import unittest
from pathlib import Path

from unittest.mock import patch

from framework.executor.models import CaseExecutionResult, SuiteExecutionResult
from framework.reporting.case_results import write_case_results
from framework.cli.main import RuntimeDependencies, build_parser, main


class FakeDriverManager:
    def __init__(self):
        self.created = False
        self.quitted = False
        self.created_drivers = []
        self.quitted_drivers = []
        self.driver = object()

    def create_driver(self, _config):
        self.created = True
        self.created_drivers.append(self.driver)
        return self.driver

    def quit_driver(self, driver):
        self.quitted = True
        self.quitted_drivers.append(driver)


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


class TrackingDriver:
    def __init__(self, name: str):
        self.name = name
        self.opened = []

    def get(self, url: str):
        self.opened.append(url)


class TrackingDriverManager:
    def __init__(self):
        self.created_drivers = []
        self.quitted_drivers = []

    def create_driver(self, _config):
        driver = TrackingDriver(name=f"driver-{len(self.created_drivers) + 1}")
        self.created_drivers.append(driver)
        return driver

    def quit_driver(self, driver):
        self.quitted_drivers.append(driver)


class TrackingActions:
    def __init__(self, driver):
        self.driver = driver

    def open(self, url: str):
        self.driver.get(url)


class TestCliRuntime(unittest.TestCase):
    def test_main_merge_results_skips_driver_creation(self):
        logger = FakeLogger()
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: (_ for _ in ()).throw(
                AssertionError("driver manager must not be created in merge mode")
            ),
            actions_factory=lambda _driver: (_ for _ in ()).throw(
                AssertionError("actions must not be created in merge mode")
            ),
            executor_factory=lambda _actions, _logger: (_ for _ in ()).throw(
                AssertionError("executor must not be created in merge mode")
            ),
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            first = tmpdir_path / "first.json"
            second = tmpdir_path / "second.json"
            write_case_results(first, [{"name": "Login", "passed": False}])
            write_case_results(second, [{"name": "Login", "passed": True}])

            rc = main(
                [
                    "--merge-results",
                    f"{first},{second}",
                ],
                dependencies=deps,
            )

        self.assertEqual(rc, 0)

    def test_main_merge_results_returns_nonzero_when_any_source_suite_teardown_failed(self):
        logger = FakeLogger()
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: (_ for _ in ()).throw(
                AssertionError("driver manager must not be created in merge mode")
            ),
            actions_factory=lambda _driver: (_ for _ in ()).throw(
                AssertionError("actions must not be created in merge mode")
            ),
            executor_factory=lambda _actions, _logger: (_ for _ in ()).throw(
                AssertionError("executor must not be created in merge mode")
            ),
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            first = tmpdir_path / "first.json"
            second = tmpdir_path / "second.json"
            write_case_results(first, [{"name": "Login", "passed": True}])
            write_case_results(
                second,
                [{"name": "Search", "passed": True}],
                suite_teardown_failed=True,
                suite_teardown_error_message="Suite teardown failed: text mismatch",
                suite_teardown_failure_type="assertion",
            )

            rc = main(
                [
                    "--merge-results",
                    f"{first},{second}",
                ],
                dependencies=deps,
            )

        self.assertEqual(rc, 1)

    def test_main_rejects_dsl_path_with_merge_results(self):
        logger = FakeLogger()
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: (_ for _ in ()).throw(
                AssertionError("driver manager must not be created when args are invalid")
            ),
            actions_factory=lambda _driver: (_ for _ in ()).throw(
                AssertionError("actions must not be created when args are invalid")
            ),
            executor_factory=lambda _actions, _logger: (_ for _ in ()).throw(
                AssertionError("executor must not be created when args are invalid")
            ),
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dsl_file = tmpdir_path / "case.xml"
            dsl_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite"><case name="Login"><step keyword="Open"><arg value="https://example.test" /></step></case></suite>
""",
                encoding="utf-8",
            )
            merged_file = tmpdir_path / "merged.json"
            write_case_results(merged_file, [{"name": "Login", "passed": True}])

            with self.assertRaises(SystemExit):
                main([str(dsl_file), "--merge-results", str(merged_file)], dependencies=deps)

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
<suite name="SmokeSuite"><case name="Login" tags="smoke"><step keyword="Open"><arg value="https://example.test" /></step></case></suite>
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
                        "workers": 1,
                    },
                )
            ],
        )

    def test_main_does_not_create_driver_until_actions_are_used(self):
        driver_manager = TrackingDriverManager()
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
            actions_factory=lambda driver: TrackingActions(driver),
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
<suite name="SmokeSuite"><case name="Login"><step keyword="Open"><arg value="https://example.test" /></step></case></suite>
""",
                encoding="utf-8",
            )

            rc = main([str(xml_file)], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertEqual(driver_manager.created_drivers, [])

    def test_main_dry_run_skips_driver_and_passes_dry_run_executor_flag(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        captured = {}
        executor = FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                case_results=[],
            )
        )

        def executor_factory(actions, _logger, keyword_libraries, listeners, dry_run):
            captured["actions"] = actions
            captured["keyword_libraries"] = keyword_libraries
            captured["listeners"] = listeners
            captured["dry_run"] = dry_run
            return executor

        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda _driver: object(),
            executor_factory=executor_factory,
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_file = Path(tmpdir) / "case.yaml"
            yaml_file.write_text(
                """
name: SmokeSuite
cases:
  - name: Login
    steps:
      - keyword: Open
        args:
          - https://example.test
""",
                encoding="utf-8",
            )
            rc = main([str(yaml_file), "--dry-run"], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertFalse(driver_manager.created)
        self.assertTrue(captured["dry_run"])
        self.assertIsNone(captured["actions"])

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
<suite name="SmokeSuite"><case name="Login"><step keyword="Open"><arg value="https://example.test" /></step></case></suite>
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
                        "workers": 1,
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
