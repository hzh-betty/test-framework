import tempfile
import unittest
from pathlib import Path

from framework.executor.runner import Executor
from framework.page_objects.base_page import BasePage


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


class TestXmlExecutionFlow(unittest.TestCase):
    def test_executor_run_file_executes_xml_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            case_file = Path(tmpdir) / "login.xml"
            case_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="SmokeSuite">
  <case name="Login success">
    <step action="open" target="https://example.test/login" />
    <step action="type" target="id=username" value="demo" />
    <step action="click" target="id=submit" />
  </case>
</suite>
""",
                encoding="utf-8",
            )
            actions = FakeActions()
            executor = Executor(page_factory=lambda: BasePage(actions=actions))

            result = executor.run_file(str(case_file))

            self.assertEqual(result.passed_cases, 1)
            self.assertEqual(
                actions.calls,
                [
                    ("open", "https://example.test/login"),
                    ("type", "id=username", "demo"),
                    ("click", "id=submit"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
