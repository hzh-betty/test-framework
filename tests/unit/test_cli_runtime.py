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
<suite name="SmokeSuite"><case name="Login"><step action="open" target="https://example.test" /></case></suite>
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
                        "workers": 1,
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
            [
                {
                    "name": "Login",
                    "passed": True,
                    "step_results": [],
                    "error_message": None,
                    "failure_type": None,
                }
            ],
            suite_teardown_failed=False,
            suite_teardown_error_message=None,
            suite_teardown_failure_type=None,
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
                        "workers": 1,
                    },
                )
            ],
        )

    def test_main_passes_workers_to_executor(self):
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
<suite name="SmokeSuite"><case name="Login"><step action="open" target="https://example.test" /></case></suite>
""",
                encoding="utf-8",
            )
            rc = main([str(xml_file), "--workers", "3"], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertEqual(executor.run_file_calls[0][1]["workers"], 3)

    def test_main_uses_isolated_drivers_per_thread_when_workers_gt_one(self):
        driver_manager = TrackingDriverManager()
        logger = FakeLogger()
        captured = {}
        lock = threading.Lock()

        class ParallelProbeExecutor:
            def __init__(self, actions):
                self.actions = actions
                self.thread_drivers = {}

            def run_file(self, _dsl_path: str, **kwargs):
                workers = kwargs["workers"]
                barrier = threading.Barrier(workers)

                def run_case(index: int):
                    barrier.wait(timeout=1)
                    self.actions.open(f"https://example.test/case-{index}")
                    with lock:
                        self.thread_drivers[threading.get_ident()] = self.actions.driver

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(run_case, index) for index in range(workers)]
                    for future in futures:
                        future.result()
                return SuiteExecutionResult(
                    name="Smoke",
                    total_cases=workers,
                    passed_cases=workers,
                    failed_cases=0,
                    case_results=[],
                )

        def executor_factory(actions, _logger):
            executor = ParallelProbeExecutor(actions)
            captured["executor"] = executor
            return executor

        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda driver: TrackingActions(driver),
            executor_factory=executor_factory,
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
            rc = main([str(xml_file), "--workers", "3"], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertEqual(len(driver_manager.created_drivers), 3)
        self.assertEqual(len(driver_manager.quitted_drivers), 3)
        self.assertEqual(
            {id(driver) for driver in driver_manager.created_drivers},
            {id(driver) for driver in driver_manager.quitted_drivers},
        )
        self.assertEqual(len(captured["executor"].thread_drivers), 3)
        self.assertEqual(
            len({id(driver) for driver in captured["executor"].thread_drivers.values()}),
            3,
        )

    def test_main_keeps_single_driver_wiring_when_workers_is_one(self):
        driver_manager = TrackingDriverManager()
        logger = FakeLogger()
        captured = {}

        class SerialProbeExecutor:
            def __init__(self, actions):
                self.actions = actions
                self.driver = None

            def run_file(self, _dsl_path: str, **kwargs):
                self.actions.open("https://example.test/serial")
                self.driver = self.actions.driver
                return SuiteExecutionResult(
                    name="Smoke",
                    total_cases=1,
                    passed_cases=1,
                    failed_cases=0,
                    case_results=[],
                )

        def executor_factory(actions, _logger):
            executor = SerialProbeExecutor(actions)
            captured["executor"] = executor
            return executor

        deps = RuntimeDependencies(
            driver_manager_factory=lambda: driver_manager,
            actions_factory=lambda driver: TrackingActions(driver),
            executor_factory=executor_factory,
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
            rc = main([str(xml_file), "--workers", "1"], dependencies=deps)

        self.assertEqual(rc, 0)
        self.assertEqual(len(driver_manager.created_drivers), 1)
        self.assertEqual(len(driver_manager.quitted_drivers), 1)
        self.assertIs(driver_manager.created_drivers[0], captured["executor"].driver)
        self.assertIs(driver_manager.quitted_drivers[0], captured["executor"].driver)

    def test_build_parser_rejects_negative_workers(self):
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["suite.xml", "--workers", "-1"])

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
        write_spy.assert_called_once_with(
            Path("artifacts/case-results.json"),
            [],
            suite_teardown_failed=False,
            suite_teardown_error_message=None,
            suite_teardown_failure_type=None,
        )

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

    def test_main_returns_nonzero_when_suite_teardown_failed(self):
        driver_manager = FakeDriverManager()
        logger = FakeLogger()
        executor = FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                case_results=[],
                suite_teardown_failed=True,
                suite_teardown_error_message="Suite teardown failed: text mismatch",
                suite_teardown_failure_type="assertion",
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
