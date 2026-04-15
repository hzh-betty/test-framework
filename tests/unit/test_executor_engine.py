import unittest
from dataclasses import dataclass

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
        self.calls.append(("screenshot", path))


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
                    steps=[StepSpec(action="hover", target="id=menu")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: FakePage(calls))

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        self.assertIn("Unsupported action", result.case_results[0].error_message)

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


if __name__ == "__main__":
    unittest.main()
