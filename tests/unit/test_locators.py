import unittest

from framework.selenium.locators import Locator, LocatorError


class TestLocators(unittest.TestCase):
    def test_parse_locator_defaults_to_css_without_prefix(self):
        locator = Locator.parse("button[type='submit']")

        self.assertEqual(locator.by, "css selector")
        self.assertEqual(locator.value, "button[type='submit']")

    def test_parse_locator_supports_known_prefixes(self):
        self.assertEqual(Locator.parse("id=username"), Locator("id", "username", "id=username"))
        self.assertEqual(
            Locator.parse("partial_link=Docs"),
            Locator("partial link text", "Docs", "partial_link=Docs"),
        )

    def test_parse_locator_rejects_unknown_prefix(self):
        with self.assertRaisesRegex(LocatorError, "Unknown locator strategy 'foo'"):
            Locator.parse("foo=bar")

    def test_parse_locator_supports_text_strategy(self):
        locator = Locator.parse("text=Submit")

        self.assertEqual(locator.by, "xpath")
        self.assertIn("normalize-space", locator.value)
        self.assertIn("Submit", locator.value)

    def test_parse_locator_supports_testid_strategy(self):
        locator = Locator.parse("data-testid=login-button")

        self.assertEqual(locator.by, "css selector")
        self.assertEqual(locator.value, '[data-testid="login-button"]')

    def test_parse_locator_rejects_empty_locator(self):
        with self.assertRaisesRegex(LocatorError, "empty locator"):
            Locator.parse(" ")


if __name__ == "__main__":
    unittest.main()
