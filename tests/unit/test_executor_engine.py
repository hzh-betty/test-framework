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
        self.assertIn("Unknown keyword", result.case_results[0].error_message)

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
