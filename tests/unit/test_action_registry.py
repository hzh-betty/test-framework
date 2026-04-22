import unittest

from framework.dsl.models import StepSpec
from framework.executor.action_registry import (
    ActionValidationError,
    default_action_registry,
    normalize_action_name,
)


class FakePage:
    def __init__(self):
        self.calls: list[tuple] = []

    def wait_visible(self, locator: str, timeout: float = 10):
        self.calls.append(("wait_visible", locator, timeout))

    def type(self, locator: str, value: str):
        self.calls.append(("type", locator, value))


class TestActionRegistry(unittest.TestCase):
    def test_normalize_action_name_uses_robot_style_matching(self):
        self.assertEqual(normalize_action_name("Wait Visible"), "wait_visible")
        self.assertEqual(normalize_action_name("wait-visible"), "wait_visible")
        self.assertEqual(normalize_action_name("wait_visible"), "wait_visible")

    def test_dispatch_normalizes_action_and_parses_timeout(self):
        page = FakePage()
        registry = default_action_registry()

        registry.dispatch(page, StepSpec(action="Wait Visible", target="id=submit", timeout="500ms"))

        self.assertEqual(page.calls, [("wait_visible", "id=submit", 0.5)])

    def test_dispatch_validates_required_value(self):
        registry = default_action_registry()

        with self.assertRaisesRegex(ActionValidationError, "Action 'type' requires value"):
            registry.dispatch(FakePage(), StepSpec(action="type", target="id=username"))

    def test_dispatch_unknown_action_recommends_candidate(self):
        registry = default_action_registry()

        with self.assertRaisesRegex(ActionValidationError, "Unknown action 'wait visibl'.*wait_visible"):
            registry.dispatch(FakePage(), StepSpec(action="wait visibl", target="id=submit"))


if __name__ == "__main__":
    unittest.main()
