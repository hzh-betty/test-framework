import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from framework.cli.main import RuntimeDependencies, main
from framework.executor.runner import Executor
from framework.page_objects.base_page import BasePage
from framework.reporting.case_results import read_case_results, write_case_results


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


class GuardDriverManager:
    def create_driver(self, _config):
        raise AssertionError("driver must not be created in this flow")

    def quit_driver(self, _driver):
        return None


class FakeActions:
    def __init__(self):
        self.calls: list[tuple] = []

    def open(self, url: str):
        self.calls.append(("open", url))

    def type(self, locator: str, value: str):
        self.calls.append(("type", locator, value))

    def click(self, locator: str):
        self.calls.append(("click", locator))

    def assert_text(self, locator: str, expected: str):
        self.calls.append(("assert_text", locator, expected))

    def wait_visible(self, locator: str, timeout: int = 10):
        self.calls.append(("wait_visible", locator, timeout))

    def screenshot(self, path: str):
        self.calls.append(("screenshot", path))


class FakeLogger:
    def info(self, _message: str):
        return None

    def error(self, _message: str):
        return None


class FakeNotifier:
    def send(self, **_kwargs):
        return None


class FakeReporter:
    def write_suite_result(self, _result, context=None):
        return Path("artifacts/allure-results/executor-summary.json")

    def write_environment_properties(self, _context):
        return Path("artifacts/allure-results/environment.properties")

    def generate_html_report(self, output_dir):
        return True


@contextmanager
def chdir(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


class TestExecutionControlFlow(unittest.TestCase):
    def test_filtering_flow_level_and_run_empty_suite(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            xml_file = tmp / "suite.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite">
  <case name="Login" tags="smoke">
    <step keyword="Open"><arg value="https://example.test/login" /></step>
  </case>
</suite>
""",
                encoding="utf-8",
            )
            deps = RuntimeDependencies(
                driver_manager_factory=lambda: GuardDriverManager(),
                actions_factory=lambda _driver: object(),
                executor_factory=lambda _actions, _logger: (_ for _ in ()).throw(
                    AssertionError("executor must not run when suite is empty")
                ),
                reporter_factory=lambda _results_dir: FakeReporter(),
                logger_factory=lambda _level, _file: FakeLogger(),
                email_notifier_factory=lambda _config: FakeNotifier(),
                dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
            )

            with chdir(tmp):
                with self.assertRaises(ValueError, msg="default empty suite should fail"):
                    main(
                        [str(xml_file), "--include-tag-expr", "regression"],
                        dependencies=deps,
                    )
                rc = main(
                    [
                        str(xml_file),
                        "--include-tag-expr",
                        "regression",
                        "--run-empty-suite",
                    ],
                    dependencies=deps,
                )

            self.assertEqual(rc, 0)
            self.assertEqual(read_case_results(tmp / "artifacts/case-results.json"), [])

    def test_rerunfailed_path_selects_failed_case_names(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            xml_file = tmp / "suite.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite">
  <case name="Login" tags="smoke">
    <step keyword="Open"><arg value="https://example.test/login" /></step>
  </case>
  <case name="Checkout" tags="smoke">
    <step keyword="Open"><arg value="https://example.test/checkout" /></step>
  </case>
</suite>
""",
                encoding="utf-8",
            )
            rerun_file = tmp / "case-results.json"
            write_case_results(
                rerun_file,
                [
                    {"name": "Login", "passed": False},
                    {"name": "Checkout", "passed": True},
                ],
            )

            actions = FakeActions()
            driver_manager = FakeDriverManager()
            deps = RuntimeDependencies(
                driver_manager_factory=lambda: driver_manager,
                actions_factory=lambda _driver: actions,
                executor_factory=lambda _actions, logger: Executor(
                    page_factory=lambda: BasePage(actions=actions),
                    logger=logger,
                ),
                reporter_factory=lambda _results_dir: FakeReporter(),
                logger_factory=lambda _level, _file: FakeLogger(),
                email_notifier_factory=lambda _config: FakeNotifier(),
                dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
            )

            with chdir(tmp):
                rc = main([str(xml_file), "--rerunfailed", str(rerun_file)], dependencies=deps)

            self.assertEqual(rc, 0)
            self.assertFalse(driver_manager.created)
            self.assertFalse(driver_manager.quitted)
            self.assertEqual(actions.calls, [("open", "https://example.test/login")])
            cases = read_case_results(tmp / "artifacts/case-results.json")
            self.assertEqual([case["name"] for case in cases], ["Login"])

    def test_merge_results_later_overrides_earlier_and_summary_follows_merged_cases(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            first = tmp / "first.json"
            second = tmp / "second.json"
            write_case_results(
                first,
                [
                    {"name": "Login", "passed": False},
                    {"name": "Search", "passed": True},
                ],
            )
            write_case_results(
                second,
                [
                    {"name": "Login", "passed": True},
                    {"name": "Checkout", "passed": False},
                ],
            )

            deps = RuntimeDependencies(
                driver_manager_factory=lambda: GuardDriverManager(),
                actions_factory=lambda _driver: object(),
                executor_factory=lambda _actions, _logger: (_ for _ in ()).throw(
                    AssertionError("executor must not run in merge mode")
                ),
                reporter_factory=lambda _results_dir: FakeReporter(),
                logger_factory=lambda _level, _file: FakeLogger(),
                email_notifier_factory=lambda _config: FakeNotifier(),
                dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
            )

            with chdir(tmp):
                rc = main(
                    ["--merge-results", f"{first},{second}"],
                    dependencies=deps,
                )

            merged_cases = read_case_results(tmp / "artifacts/case-results.json")
            by_name = {case["name"]: case["passed"] for case in merged_cases}

            self.assertEqual(rc, 1)
            self.assertEqual(by_name["Login"], True)
            self.assertEqual(by_name["Search"], True)
            self.assertEqual(by_name["Checkout"], False)
            self.assertEqual(len(merged_cases), 3)
            self.assertEqual(sum(1 for case in merged_cases if case["passed"] is False), 1)


if __name__ == "__main__":
    unittest.main()
