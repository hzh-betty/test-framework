import unittest

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.executor.runner import Executor


class FakeLogger:
    def __init__(self):
        self.info_messages: list[str] = []
        self.error_messages: list[str] = []

    def info(self, message: str):
        self.info_messages.append(message)

    def error(self, message: str):
        self.error_messages.append(message)


class FakePage:
    def __init__(self):
        self.screenshots: list[str] = []

    def assert_text(self, locator: str, expected: str):
        raise AssertionError("text mismatch")

    def screenshot(self, path: str):
        self.screenshots.append(path)


class TestExecutorLoggingIntegration(unittest.TestCase):
    def test_failure_logs_context_and_captures_screenshot(self):
        logger = FakeLogger()
        page = FakePage()
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="Login",
                    steps=[StepSpec(action="assert_text", target="id=welcome", value="FAIL")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: page, logger=logger)

        result = executor.run_suite(suite)

        self.assertEqual(result.failed_cases, 1)
        self.assertEqual(len(page.screenshots), 1)
        self.assertIn("locator=id=welcome", logger.error_messages[0])
        self.assertIn("screenshot=", logger.error_messages[0])

    def test_screenshot_failure_does_not_override_original_step_error(self):
        logger = FakeLogger()

        class ScreenshotFailPage(FakePage):
            def screenshot(self, path: str):
                raise RuntimeError("cannot save screenshot")

        page = ScreenshotFailPage()
        suite = SuiteSpec(
            name="Smoke",
            cases=[
                CaseSpec(
                    name="Login",
                    steps=[StepSpec(action="assert_text", target="id=welcome", value="FAIL")],
                )
            ],
        )
        executor = Executor(page_factory=lambda: page, logger=logger)

        result = executor.run_suite(suite)

        self.assertEqual(result.case_results[0].error_message, "text mismatch")


if __name__ == "__main__":
    unittest.main()
