import unittest
from pathlib import Path

from framework.keywords.arguments import bind_keyword_arguments
from framework.selenium.locators import Locator


def sample(locator: Locator, text: str, count: int = 1, enabled: bool = False):
    return locator, text, count, enabled


def with_path(path: Path, timeout: float):
    return path, timeout


class TestKeywordArguments(unittest.TestCase):
    def test_binds_positional_kwargs_defaults_and_converts_types(self):
        bound = bind_keyword_arguments(
            sample,
            args=["id=login", "Submit"],
            kwargs={"count": "3", "enabled": "yes"},
        )

        self.assertEqual(bound.args[0].raw, "id=login")
        self.assertEqual(bound.args[1:], ("Submit", 3, True))
        self.assertEqual(bound.kwargs, {})

    def test_converts_path_and_positive_timeout(self):
        bound = bind_keyword_arguments(
            with_path,
            args=["artifacts/report.txt"],
            kwargs={"timeout": "500ms"},
        )

        self.assertEqual(bound.args, (Path("artifacts/report.txt"), 0.5))

    def test_reports_missing_unknown_and_duplicate_arguments(self):
        with self.assertRaisesRegex(ValueError, "missing required argument: text"):
            bind_keyword_arguments(sample, args=["id=login"], kwargs={})
        with self.assertRaisesRegex(ValueError, "unexpected keyword argument: nope"):
            bind_keyword_arguments(sample, args=["id=login", "Submit"], kwargs={"nope": "x"})
        with self.assertRaisesRegex(ValueError, "multiple values for argument: text"):
            bind_keyword_arguments(
                sample,
                args=["id=login", "Submit"],
                kwargs={"text": "Duplicate"},
            )

    def test_rejects_invalid_locator_timeout_and_bool(self):
        with self.assertRaisesRegex(ValueError, "Unknown locator strategy"):
            bind_keyword_arguments(sample, args=["foo=bar", "Submit"], kwargs={})
        with self.assertRaisesRegex(ValueError, "must be positive"):
            bind_keyword_arguments(with_path, args=["out.txt"], kwargs={"timeout": "0"})
        with self.assertRaisesRegex(ValueError, "boolean"):
            bind_keyword_arguments(sample, args=["id=login", "Submit"], kwargs={"enabled": "maybe"})


if __name__ == "__main__":
    unittest.main()
