import unittest
from dataclasses import dataclass
import tempfile
from pathlib import Path
import threading
import time

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.executor.runner import Executor


@dataclass
class FakePage:
    calls: list[tuple]

    def open(self, url: str):
        self.calls.append(("open", url))

    def click(self, locator: str):
        self.calls.append(("click", locator))

    def type(self, locator: str, value: str):
        self.calls.append(("type", locator, value))

    def assert_text(self, locator: str, expected: str):
        self.calls.append(("assert_text", locator, expected))
        if expected == "FAIL":
            raise AssertionError("text mismatch")

    def wait_visible(self, locator: str, timeout: int = 10):
        self.calls.append(("wait_visible", locator, timeout))

    def screenshot(self, path: str):
        if "/screenshots/" not in path:
            self.calls.append(("screenshot", path))

    def wait_clickable(self, locator: str, timeout: int = 10):
        self.calls.append(("wait_clickable", locator, timeout))

    def wait_text(self, locator: str, expected: str, timeout: int = 10):
        self.calls.append(("wait_text", locator, expected, timeout))

    def wait_url_contains(self, fragment: str, timeout: int = 10):
        self.calls.append(("wait_url_contains", fragment, timeout))

    def assert_element_visible(self, locator: str, timeout: int = 10):
        self.calls.append(("assert_element_visible", locator, timeout))

    def assert_element_contains(self, locator: str, expected: str):
        self.calls.append(("assert_element_contains", locator, expected))

    def select(self, locator: str, option_text: str):
        self.calls.append(("select", locator, option_text))

    def hover(self, locator: str):
        self.calls.append(("hover", locator))

    def switch_frame(self, frame_reference: str):
        self.calls.append(("switch_frame", frame_reference))

    def switch_window(self, window_reference: str):
        self.calls.append(("switch_window", window_reference))

    def accept_alert(self, timeout: int = 10):
        self.calls.append(("accept_alert", timeout))

    def upload_file(self, locator: str, file_path: str):
        self.calls.append(("upload_file", locator, file_path))

    def clear(self, locator: str):
        self.calls.append(("clear", locator))

    def wait_not_visible(self, locator: str, timeout: float = 10):
        self.calls.append(("wait_not_visible", locator, timeout))

    def wait_gone(self, locator: str, timeout: float = 10):
        self.calls.append(("wait_gone", locator, timeout))

    def assert_url_contains(self, fragment: str):
        self.calls.append(("assert_url_contains", fragment))

    def assert_title_contains(self, expected: str):
        self.calls.append(("assert_title_contains", expected))

    def new_browser(self, alias: str = "default"):
        self.calls.append(("new_browser", alias))

    def switch_browser(self, alias: str):
        self.calls.append(("switch_browser", alias))

    def close_browser(self, alias: str | None = None):
        self.calls.append(("close_browser", alias))


class DiagnosticDriver:
    current_url = "https://example.test/login"
    title = "Login"
    page_source = "<html><body>Login</body></html>"


class DiagnosticActions:
    def __init__(self):
        self.driver = DiagnosticDriver()
        self.current_alias = "admin"


class DiagnosticPage(FakePage):
    def __init__(self, calls: list[tuple], root: Path):
        super().__init__(calls)
        self.actions = DiagnosticActions()
        self.root = root

    def assert_text(self, locator: str, expected: str):
        super().assert_text(locator, expected)
        raise AssertionError("text mismatch")

    def screenshot(self, path: str):
        self.calls.append(("screenshot", path))
        screenshot = Path(path)
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_bytes(b"fake-png")


class TestExecutorEngine(unittest.TestCase):
    def test_run_suite_executes_case_steps_in_order(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="Login",
                    steps=[
                        StepSpec(action="open", target="https://example.test"),
                        StepSpec(action="type", target="id=username", value="demo"),
                        StepSpec(action="click", target="id=submit"),
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.total_cases, 1)
        self.assertEqual(result.passed_cases, 1)
        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(
            calls,
            [
                ("open", "https://example.test"),
                ("type", "id=username", "demo"),
                ("click", "id=submit"),
            ],
        )

    def test_run_suite_marks_case_failed_and_stops_next_steps(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="AssertionCase",
                    steps=[
                        StepSpec(action="assert_text", target="id=title", value="FAIL"),
                        StepSpec(action="click", target="id=never"),
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.passed_cases, 0)
        self.assertEqual(result.failed_cases, 1)
        self.assertEqual(calls, [("assert_text", "id=title", "FAIL")])

    def test_unknown_action_fails_case(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="UnknownAction",
                    steps=[StepSpec(action="drag", target="id=menu")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        self.assertIn("Unknown action", result.case_results[0].error_message)

    def test_extended_actions_are_dispatched_to_page_layer(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="ExtendedActions",
                    steps=[
                        StepSpec(action="wait_clickable", target="id=submit", value="3"),
                        StepSpec(action="wait_text", target="id=status", value="Done"),
                        StepSpec(action="wait_url_contains", target="/dashboard", value="4"),
                        StepSpec(action="assert_element_visible", target="id=title", value="5"),
                        StepSpec(
                            action="assert_element_contains",
                            target="id=title",
                            value="Welcome",
                        ),
                        StepSpec(action="select", target="id=country", value="China"),
                        StepSpec(action="hover", target="id=menu"),
                        StepSpec(action="switch_frame", target="id=main-frame"),
                        StepSpec(action="switch_window", target="1"),
                        StepSpec(action="accept_alert", target="alert", value="6"),
                        StepSpec(
                            action="upload_file",
                            target="id=upload",
                            value="fixtures/demo.txt",
                        ),
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(
            calls,
            [
                ("wait_clickable", "id=submit", 3),
                ("wait_text", "id=status", "Done", 10),
                ("wait_url_contains", "/dashboard", 4),
                ("assert_element_visible", "id=title", 5),
                ("assert_element_contains", "id=title", "Welcome"),
                ("select", "id=country", "China"),
                ("hover", "id=menu"),
                ("switch_frame", "id=main-frame"),
                ("switch_window", "1"),
                ("accept_alert", 6),
                ("upload_file", "id=upload", "fixtures/demo.txt"),
            ],
        )

    def test_wait_text_does_not_parse_legacy_inline_timeout_suffix(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="WaitTextTimeout",
                    steps=[
                        StepSpec(
                            action="wait_text",
                            target="id=status",
                            value="Done|timeout=7",
                        )
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(calls, [("wait_text", "id=status", "Done|timeout=7", 10.0)])

    def test_timeout_field_is_dispatched_to_wait_action(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="TimeoutField",
                    steps=[
                        StepSpec(
                            action="Wait Visible",
                            target="id=status",
                            timeout="500ms",
                        )
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(calls, [("wait_visible", "id=status", 0.5)])

    def test_new_stable_core_actions_are_dispatched(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="StableActions",
                    steps=[
                        StepSpec(action="clear", target="id=query"),
                        StepSpec(action="wait_not_visible", target="id=spinner", timeout="2s"),
                        StepSpec(action="wait_gone", target="id=toast", timeout="2s"),
                        StepSpec(action="assert_url_contains", target="/dashboard"),
                        StepSpec(action="assert_title_contains", target="Dashboard"),
                        StepSpec(action="new_browser", target="admin"),
                        StepSpec(action="switch_browser", target="admin"),
                        StepSpec(action="close_browser", target="admin"),
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(
            calls,
            [
                ("clear", "id=query"),
                ("wait_not_visible", "id=spinner", 2.0),
                ("wait_gone", "id=toast", 2.0),
                ("assert_url_contains", "/dashboard"),
                ("assert_title_contains", "Dashboard"),
                ("new_browser", "admin"),
                ("switch_browser", "admin"),
                ("close_browser", "admin"),
            ],
        )

    def test_failed_step_records_browser_diagnostics_and_artifacts(self):
        calls: list[tuple] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            suite = SuiteSpec(
                name="Smoke",
                cases=[
                    CaseSpec(
                        name="Login Failure",
                        steps=[StepSpec(action="assert_text", target="id=title", value="FAIL")],
                    )
                ],
            )
            executor = Executor(
                page_factory=lambda: DiagnosticPage(calls, root),
                screenshot_dir=str(root / "screenshots"),
                page_source_dir=str(root / "page-source"),
            )

            result = executor.run_suite(suite)
            step = result.case_results[0].step_results[0]

            self.assertEqual(result.failed_cases, 1)
            self.assertEqual(step.browser_alias, "admin")
            self.assertEqual(step.page_title, "Login")
            self.assertIsNotNone(step.screenshot_path)
            self.assertIsNotNone(step.page_source_path)
            self.assertTrue(Path(step.screenshot_path).exists())
            self.assertTrue(Path(step.page_source_path).exists())

    def test_parse_wait_text_value_rejects_empty_timeout_suffix(self):
        executor = Executor(page_factory=lambda: FakePage([]))

        with self.assertRaisesRegex(ValueError, "timeout must be a positive integer"):
            executor._parse_wait_text_value("Done|timeout=")

    def test_parse_wait_text_value_rejects_non_integer_timeout_suffix(self):
        executor = Executor(page_factory=lambda: FakePage([]))

        with self.assertRaisesRegex(ValueError, "timeout must be a positive integer"):
            executor._parse_wait_text_value("Done|timeout=fast")

    def test_parse_wait_text_value_rejects_non_positive_timeout_suffix(self):
        executor = Executor(page_factory=lambda: FakePage([]))

        with self.assertRaisesRegex(ValueError, "timeout must be a positive integer"):
            executor._parse_wait_text_value("Done|timeout=0")

    def test_run_suite_fails_when_filtered_empty_and_not_allowed(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="Login",
                    tags=["smoke"],
                    steps=[StepSpec(action="open", target="https://example.test")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        with self.assertRaisesRegex(
            ValueError, "Suite contains no runnable cases after filtering."
        ):
            executor.run_suite(
                suite,
                include_tag_expr="regression",
                run_empty_suite=False,
            )

    def test_run_suite_succeeds_when_filtered_empty_and_allowed(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="Login",
                    tags=["smoke"],
                    steps=[StepSpec(action="open", target="https://example.test")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(
            suite,
            include_tag_expr="regression",
            run_empty_suite=True,
        )

        self.assertEqual(result.total_cases, 0)
        self.assertEqual(result.passed_cases, 0)
        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(result.case_results, [])

    def test_run_suite_raises_for_empty_tag_expression(self):
        suite = SuiteSpec(
            name="Smoke",
            cases=[CaseSpec(name="Login", tags=["smoke"], steps=[])],
        )
        executor = Executor(page_factory=lambda: FakePage([]))

        with self.assertRaisesRegex(ValueError, "Tag expression is empty"):
            executor.run_suite(suite, include_tag_expr="")

    def test_run_suite_include_only_behavior(self):
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(name="Login", tags=["smoke"], steps=[]),
                CaseSpec(name="Checkout", tags=["regression"], steps=[]),
            ],
        )
        executor = Executor(page_factory=lambda: FakePage([]))

        result = executor.run_suite(suite, include_tag_expr="smoke")

        self.assertEqual(result.total_cases, 1)
        self.assertEqual([case.name for case in result.case_results], ["Login"])

    def test_run_suite_exclude_only_behavior(self):
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(name="Login", tags=["smoke"], steps=[]),
                CaseSpec(name="FlakyCase", tags=["smoke", "flaky"], steps=[]),
            ],
        )
        executor = Executor(page_factory=lambda: FakePage([]))

        result = executor.run_suite(suite, exclude_tag_expr="flaky")

        self.assertEqual(result.total_cases, 1)
        self.assertEqual([case.name for case in result.case_results], ["Login"])

    def test_run_suite_combines_include_and_exclude_filters(self):
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(name="Login", tags=["smoke"], steps=[]),
                CaseSpec(name="Checkout", tags=["regression"], steps=[]),
                CaseSpec(name="FlakyLogin", tags=["smoke", "flaky"], steps=[]),
            ],
        )
        executor = Executor(page_factory=lambda: FakePage([]))

        result = executor.run_suite(
            suite,
            include_tag_expr="smoke OR regression",
            exclude_tag_expr="flaky",
        )

        self.assertEqual(result.total_cases, 2)
        self.assertEqual(
            [case.name for case in result.case_results],
            ["Login", "Checkout"],
        )

    def test_run_suite_allowed_case_names_interact_with_tag_filters(self):
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(name="Login", tags=["smoke"], steps=[]),
                CaseSpec(name="Checkout", tags=["smoke", "flaky"], steps=[]),
                CaseSpec(name="Profile", tags=["smoke"], steps=[]),
            ],
        )
        executor = Executor(page_factory=lambda: FakePage([]))

        result = executor.run_suite(
            suite,
            include_tag_expr="smoke",
            exclude_tag_expr="flaky",
            allowed_case_names={"Login", "Checkout"},
        )

        self.assertEqual(result.total_cases, 1)
        self.assertEqual([case.name for case in result.case_results], ["Login"])

    def test_run_suite_executes_nested_keywords_with_traceable_call_chain(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            variables={"base_url": "https://example.test", "username": "suite-user"},
            keywords={
                "login": [
                    StepSpec(action="open", target="${base_url}/login"),
                    StepSpec(action="type", target="id=username", value="${username}"),
                ],
                "submit-login": [
                    StepSpec(action="call", target="login"),
                    StepSpec(action="click", target="id=submit"),
                ],
            },
            cases=[
                CaseSpec(
                    name="Login",
                    variables={"username": "case-user"},
                    steps=[StepSpec(action="call", target="submit-login")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(
            calls,
            [
                ("open", "https://example.test/login"),
                ("type", "id=username", "case-user"),
                ("click", "id=submit"),
            ],
        )
        step_results = result.case_results[0].step_results
        open_step = next(step for step in step_results if step.action == "open")
        click_step = next(step for step in step_results if step.action == "click")
        self.assertEqual(open_step.call_chain, ["submit-login", "login"])
        self.assertEqual(click_step.call_chain, ["submit-login"])

    def test_run_suite_substitutes_case_variables_over_suite_variables(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            variables={"base_url": "https://suite.example", "username": "suite-user"},
            cases=[
                CaseSpec(
                    name="Login",
                    variables={"base_url": "https://case.example", "username": "case-user"},
                    steps=[
                        StepSpec(action="open", target="${base_url}/login"),
                        StepSpec(action="type", target="id=username", value="${username}"),
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(
            calls,
            [
                ("open", "https://case.example/login"),
                ("type", "id=username", "case-user"),
            ],
        )

    def test_run_suite_detects_recursive_keyword_calls(self):
        suite = SuiteSpec(
            name="Smoke",
            keywords={
                "first": [StepSpec(action="call", target="second")],
                "second": [StepSpec(action="call", target="first")],
            },
            cases=[CaseSpec(name="Recursive", steps=[StepSpec(action="call", target="first")])],
        )
        executor = Executor(page_factory=lambda: FakePage([]))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        self.assertIn(
            "Recursive keyword call detected: first -> second -> first",
            result.case_results[0].error_message,
        )

    def test_run_suite_fails_for_undefined_keyword_with_failed_step_call_chain(self):
        suite = SuiteSpec(
            name="Smoke",
            keywords={
                "wrapper": [StepSpec(action="call", target="missing")],
            },
            cases=[CaseSpec(name="MissingKeyword", steps=[StepSpec(action="call", target="wrapper")])],
        )
        executor = Executor(page_factory=lambda: FakePage([]))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        case_result = result.case_results[0]
        self.assertIn("Keyword 'missing' is not defined.", case_result.error_message)
        self.assertIn("call_chain: wrapper", case_result.error_message)
        failed_missing_step = next(
            step
            for step in case_result.step_results
            if step.action == "call" and step.target == "missing"
        )
        self.assertFalse(failed_missing_step.passed)
        self.assertEqual(failed_missing_step.call_chain, ["wrapper"])

    def test_run_suite_fails_for_undefined_variable_with_failed_step_call_chain(self):
        suite = SuiteSpec(
            name="Smoke",
            keywords={
                "fill-username": [
                    StepSpec(action="type", target="id=username", value="${username}")
                ]
            },
            cases=[
                CaseSpec(
                    name="MissingVariable",
                    steps=[StepSpec(action="call", target="fill-username")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage([]))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        case_result = result.case_results[0]
        self.assertIn(
            "Undefined variable 'username' in step value",
            case_result.error_message,
        )
        self.assertIn("call_chain: fill-username", case_result.error_message)
        failed_type_step = next(
            step
            for step in case_result.step_results
            if step.action == "type" and step.target == "id=username"
        )
        self.assertFalse(failed_type_step.passed)
        self.assertEqual(failed_type_step.call_chain, ["fill-username"])

    def test_run_suite_without_keyword_call_keeps_empty_call_chain(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="Login",
                    steps=[StepSpec(action="open", target="https://example.test")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(result.case_results[0].step_results[0].call_chain, [])

    def test_run_suite_executes_lifecycle_hooks_in_order(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            setup=[StepSpec(action="open", target="https://example.test/before-all")],
            teardown=[StepSpec(action="screenshot", target="artifacts/after-all.png")],
            cases=[
                CaseSpec(
                    name="Login",
                    setup=[StepSpec(action="wait_visible", target="id=form")],
                    steps=[StepSpec(action="click", target="id=submit")],
                    teardown=[StepSpec(action="screenshot", target="artifacts/after-case.png")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(
            calls,
            [
                ("open", "https://example.test/before-all"),
                ("wait_visible", "id=form", 10),
                ("click", "id=submit"),
                ("screenshot", "artifacts/after-case.png"),
                ("screenshot", "artifacts/after-all.png"),
            ],
        )

    def test_run_suite_runs_case_teardown_even_when_case_fails(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="FailThenTeardown",
                    steps=[
                        StepSpec(action="assert_text", target="id=title", value="FAIL"),
                        StepSpec(action="click", target="id=never"),
                    ],
                    teardown=[StepSpec(action="screenshot", target="artifacts/case-failed.png")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        self.assertEqual(
            calls,
            [
                ("assert_text", "id=title", "FAIL"),
                ("screenshot", "artifacts/case-failed.png"),
            ],
        )

    def test_run_suite_runs_suite_teardown_even_when_some_cases_fail(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            teardown=[StepSpec(action="screenshot", target="artifacts/suite-finished.png")],
            cases=[
                CaseSpec(
                    name="FailingCase",
                    steps=[StepSpec(action="assert_text", target="id=title", value="FAIL")],
                ),
                CaseSpec(
                    name="PassingCase",
                    steps=[StepSpec(action="open", target="https://example.test/pass")],
                ),
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.passed_cases, 1)
        self.assertEqual(result.failed_cases, 1)
        self.assertEqual(
            calls,
            [
                ("assert_text", "id=title", "FAIL"),
                ("open", "https://example.test/pass"),
                ("screenshot", "artifacts/suite-finished.png"),
            ],
        )

    def test_run_suite_executes_cases_in_parallel_and_preserves_case_result_order(self):
        calls: list[tuple] = []
        state = {"active_cases": 0, "max_active_cases": 0}
        lock = threading.Lock()
        case_barrier = threading.Barrier(2)

        class ParallelPage(FakePage):
            def open(self, url: str):
                if not url.startswith("case:"):
                    super().open(url)
                    return
                with lock:
                    state["active_cases"] += 1
                    state["max_active_cases"] = max(
                        state["max_active_cases"],
                        state["active_cases"],
                    )
                try:
                    case_barrier.wait(timeout=1)
                    if url.endswith("slow"):
                        time.sleep(0.05)
                    super().open(url)
                finally:
                    with lock:
                        state["active_cases"] -= 1

        suite = SuiteSpec(
            name="Smoke",
            setup=[StepSpec(action="open", target="suite:setup")],
            teardown=[StepSpec(action="open", target="suite:teardown")],
            cases=[
                CaseSpec(name="CaseSlow", steps=[StepSpec(action="open", target="case:slow")]),
                CaseSpec(name="CaseFast", steps=[StepSpec(action="open", target="case:fast")]),
            ],
        )
        executor = Executor(page_factory=lambda: ParallelPage(calls))

        result = executor.run_suite(suite, workers=2)

        self.assertEqual(result.total_cases, 2)
        self.assertEqual(result.passed_cases, 2)
        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(
            [case_result.name for case_result in result.case_results],
            ["CaseSlow", "CaseFast"],
        )
        self.assertEqual(calls[0], ("open", "suite:setup"))
        self.assertEqual(calls[-1], ("open", "suite:teardown"))
        self.assertEqual(calls.count(("open", "suite:setup")), 1)
        self.assertEqual(calls.count(("open", "suite:teardown")), 1)
        self.assertEqual(state["max_active_cases"], 2)

    def test_run_suite_uses_serial_execution_when_workers_is_zero(self):
        calls: list[tuple] = []
        state = {"active_cases": 0, "max_active_cases": 0}
        lock = threading.Lock()

        class TrackingPage(FakePage):
            def open(self, url: str):
                if not url.startswith("case:"):
                    super().open(url)
                    return
                with lock:
                    state["active_cases"] += 1
                    state["max_active_cases"] = max(
                        state["max_active_cases"],
                        state["active_cases"],
                    )
                try:
                    time.sleep(0.01)
                    super().open(url)
                finally:
                    with lock:
                        state["active_cases"] -= 1

        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(name="CaseA", steps=[StepSpec(action="open", target="case:a")]),
                CaseSpec(name="CaseB", steps=[StepSpec(action="open", target="case:b")]),
            ],
        )
        executor = Executor(page_factory=lambda: TrackingPage(calls))

        result = executor.run_suite(suite, workers=0)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(state["max_active_cases"], 1)

    def test_run_suite_exposes_suite_teardown_failure_in_suite_status(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            teardown=[StepSpec(action="assert_text", target="id=title", value="FAIL")],
            cases=[
                CaseSpec(
                    name="PassingCase",
                    steps=[StepSpec(action="open", target="https://example.test/pass")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.passed_cases, 1)
        self.assertEqual(result.failed_cases, 0)
        self.assertTrue(result.suite_teardown_failed)
        self.assertEqual(result.suite_teardown_failure_type, "assertion")
        self.assertIn("Suite teardown failed", result.suite_teardown_error_message)
        self.assertEqual(
            calls,
            [
                ("open", "https://example.test/pass"),
                ("assert_text", "id=title", "FAIL"),
            ],
        )

    def test_run_suite_retries_step_before_failing_case(self):
        class FlakyClickPage(FakePage):
            def __init__(self, calls: list[tuple], state: dict[str, int]):
                super().__init__(calls)
                self._state = state

            def click(self, locator: str):
                self._state["click_attempts"] = self._state.get("click_attempts", 0) + 1
                super().click(locator)
                if locator == "id=flaky" and self._state["click_attempts"] < 2:
                    raise RuntimeError("transient click failure")

        calls: list[tuple] = []
        state: dict[str, int] = {}
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="StepRetry",
                    steps=[StepSpec(action="click", target="id=flaky", retry=2)],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FlakyClickPage(calls, state))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(state["click_attempts"], 2)

    def test_run_suite_records_step_observability_with_retry_trace(self):
        class DriverStub:
            current_url = "https://example.test/dashboard"

        class ActionsStub:
            driver = DriverStub()

        class FlakyClickPage(FakePage):
            def __init__(self, calls: list[tuple], state: dict[str, int]):
                super().__init__(calls)
                self._state = state
                self.actions = ActionsStub()

            def click(self, locator: str):
                self._state["click_attempts"] = self._state.get("click_attempts", 0) + 1
                super().click(locator)
                if self._state["click_attempts"] == 1:
                    raise RuntimeError("transient click failure")

        calls: list[tuple] = []
        state: dict[str, int] = {}
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="StepRetryObservability",
                    steps=[StepSpec(action="click", target="id=flaky", retry=1)],
                )
            ],
        )
        result = Executor(page_factory=lambda: FlakyClickPage(calls, state)).run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        step = result.case_results[0].step_results[0]
        self.assertIsInstance(step.duration_ms, int)
        self.assertGreaterEqual(step.duration_ms, 0)
        self.assertEqual(step.retry_attempt, 2)
        self.assertEqual(step.retry_max_retries, 1)
        self.assertEqual(step.case_attempt, 1)
        self.assertEqual(step.case_max_retries, 0)
        self.assertEqual(
            step.retry_trace,
            [
                {"attempt": 1, "status": "failed", "error": "transient click failure"},
                {"attempt": 2, "status": "passed"},
            ],
        )
        self.assertEqual(
            step.resolved_locator,
            {"raw": "id=flaky", "by": "id", "value": "flaky"},
        )
        self.assertEqual(step.current_url, "https://example.test/dashboard")

    def test_run_suite_retries_case_with_setup_and_teardown_per_attempt(self):
        class FlakyAssertionPage(FakePage):
            def __init__(self, calls: list[tuple], state: dict[str, int]):
                super().__init__(calls)
                self._state = state

            def assert_text(self, locator: str, expected: str):
                self._state["assert_attempts"] = self._state.get("assert_attempts", 0) + 1
                super().assert_text(locator, expected)
                if self._state["assert_attempts"] == 1:
                    raise AssertionError("flaky assertion")

        calls: list[tuple] = []
        state: dict[str, int] = {}
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="CaseRetry",
                    retry=1,
                    setup=[StepSpec(action="open", target="https://example.test/setup")],
                    steps=[StepSpec(action="assert_text", target="id=title", value="OK")],
                    teardown=[StepSpec(action="screenshot", target="artifacts/case-retry.png")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FlakyAssertionPage(calls, state))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(state["assert_attempts"], 2)
        self.assertEqual(
            calls,
            [
                ("open", "https://example.test/setup"),
                ("assert_text", "id=title", "OK"),
                ("screenshot", "artifacts/case-retry.png"),
                ("open", "https://example.test/setup"),
                ("assert_text", "id=title", "OK"),
                ("screenshot", "artifacts/case-retry.png"),
            ],
        )
        step = result.case_results[0].step_results[0]
        self.assertEqual(step.case_attempt, 2)
        self.assertEqual(step.case_max_retries, 1)


    def test_case_continue_on_failure_allows_following_steps_but_case_still_fails(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="ContinueCase",
                    continue_on_failure=True,
                    steps=[
                        StepSpec(action="assert_text", target="id=title", value="FAIL"),
                        StepSpec(action="click", target="id=after-failure"),
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        self.assertEqual(
            calls,
            [
                ("assert_text", "id=title", "FAIL"),
                ("click", "id=after-failure"),
            ],
        )

    def test_step_continue_on_failure_allows_following_steps_when_case_flag_disabled(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="ContinueStep",
                    steps=[
                        StepSpec(
                            action="assert_text",
                            target="id=title",
                            value="FAIL",
                            continue_on_failure=True,
                        ),
                        StepSpec(action="click", target="id=after-failure"),
                    ],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        self.assertEqual(
            calls,
            [
                ("assert_text", "id=title", "FAIL"),
                ("click", "id=after-failure"),
            ],
        )

    def test_failure_classification_is_recorded_for_case_and_step_results(self):
        class ClassificationPage(FakePage):
            def assert_text(self, locator: str, expected: str):
                super().assert_text(locator, expected)
                if expected == "TIMEOUT":
                    raise TimeoutError("assertion timed out")

            def click(self, locator: str):
                super().click(locator)
                if locator == "id=runtime":
                    raise RuntimeError("boom")

            def wait_visible(self, locator: str, timeout: int = 10):
                super().wait_visible(locator, timeout)
                if locator == "id=slow":
                    raise TimeoutError("timed out")

        def _run_single_step(step: StepSpec) -> tuple[str | None, str | None]:
            suite = SuiteSpec(name="Smoke", cases=[CaseSpec(name="Case", steps=[step])])
            result = Executor(page_factory=lambda: ClassificationPage([])).run_suite(suite)
            case = result.case_results[0]
            return case.failure_type, case.step_results[0].failure_type

        self.assertEqual(
            _run_single_step(StepSpec(action="assert_text", target="id=title", value="FAIL")),
            ("assertion", "assertion"),
        )
        self.assertEqual(
            _run_single_step(StepSpec(action="wait_visible", target="id=slow")),
            ("timeout", "timeout"),
        )
        self.assertEqual(
            _run_single_step(StepSpec(action="assert_text", target="id=title", value="TIMEOUT")),
            ("timeout", "timeout"),
        )
        self.assertEqual(
            _run_single_step(StepSpec(action="drag", target="id=menu")),
            ("action", "action"),
        )
        self.assertEqual(
            _run_single_step(StepSpec(action="click", target="id=runtime")),
            ("unknown", "unknown"),
        )


if __name__ == "__main__":
    unittest.main()
