import unittest
from dataclasses import dataclass

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.executor.listener import ExecutionListener
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

    def wait_visible(self, locator: str, timeout: float = 10):
        self.calls.append(("wait_visible", locator, timeout))

    def assert_text(self, locator: str, expected: str):
        self.calls.append(("assert_text", locator, expected))
        if expected == "FAIL":
            raise AssertionError("text mismatch")

    def screenshot(self, path: str):
        self.calls.append(("screenshot", path))


class RecordingListener(ExecutionListener):
    def __init__(self):
        self.events: list[str] = []

    def start_suite(self, suite):
        self.events.append(f"start_suite:{suite.name}")

    def end_suite(self, suite, result):
        self.events.append(f"end_suite:{result.name}")

    def start_case(self, case):
        self.events.append(f"start_case:{case.name}")

    def end_case(self, case, result):
        self.events.append(f"end_case:{result.name}")

    def start_step(self, step):
        self.events.append(f"start_step:{step.keyword}")

    def end_step(self, step, result):
        self.events.append(f"end_step:{result.keyword_name}:{result.passed}")


class FailingListener(ExecutionListener):
    def end_step(self, step, result):
        raise RuntimeError("listener failed")


class TestKeywordExecutor(unittest.TestCase):
    def test_executes_keyword_steps_with_args_kwargs_and_timeout(self):
        calls: list[tuple] = []
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="Login",
                    steps=[
                        StepSpec(keyword="Open", args=["https://example.test"]),
                        StepSpec(keyword="Type Text", args=["id=username", "demo"]),
                        StepSpec(keyword="Wait Visible", args=["id=submit"], timeout="500ms"),
                        StepSpec(keyword="Click", args=["id=submit"]),
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
                ("open", "https://example.test"),
                ("type", "id=username", "demo"),
                ("wait_visible", "id=submit", 0.5),
                ("click", "id=submit"),
            ],
        )
        self.assertEqual(result.case_results[0].step_results[0].keyword_name, "Open")
        self.assertEqual(result.case_results[0].step_results[0].arguments, ["https://example.test"])

    def test_unknown_keyword_fails_with_recommendation(self):
        suite = SuiteSpec(
            name="Smoke",
            cases=[CaseSpec(name="Typo", steps=[StepSpec(keyword="Clik", args=["id=submit"])])],
        )
        result = Executor(page_factory=lambda: FakePage([])).run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        self.assertIn("Unknown keyword 'Clik'", result.case_results[0].error_message)
        self.assertIn("Did you mean: Click", result.case_results[0].error_message)

    def test_listeners_receive_events_and_errors_are_diagnostics(self):
        listener = RecordingListener()
        failing = FailingListener()
        suite = SuiteSpec(
            name="Smoke",
            cases=[CaseSpec(name="Login", steps=[StepSpec(keyword="Open", args=["/"])])],
        )
        result = Executor(
            page_factory=lambda: FakePage([]),
            listeners=[listener, failing],
        ).run_suite(suite)

        self.assertEqual(result.failed_cases, 0)
        self.assertEqual(
            listener.events,
            [
                "start_suite:Smoke",
                "start_case:Login",
                "start_step:Open",
                "end_step:Open:True",
                "end_case:Login",
                "end_suite:Smoke",
            ],
        )
        self.assertIn("listener failed", result.case_results[0].step_results[0].diagnostics["listener_errors"][0])

    def test_dry_run_validates_without_page_factory_or_browser_actions(self):
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="Dry",
                    steps=[
                        StepSpec(keyword="Wait Visible", args=["id=submit"], timeout="2s"),
                        StepSpec(keyword="Click", args=["unknown=submit"]),
                    ],
                )
            ],
        )
        created = False

        def page_factory():
            nonlocal created
            created = True
            return FakePage([])

        result = Executor(page_factory=page_factory, dry_run=True).run_suite(suite)

        self.assertFalse(created)
        self.assertEqual(result.failed_cases, 1)
        self.assertTrue(result.case_results[0].step_results[0].dry_run)
        self.assertEqual(result.case_results[0].step_results[0].keyword_name, "Wait Visible")
        self.assertEqual(result.case_results[0].failure_type, "locator")


if __name__ == "__main__":
    unittest.main()
