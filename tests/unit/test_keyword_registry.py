import unittest

from framework.keywords import KeywordRegistry, keyword, library, not_keyword


class TestKeywordRegistry(unittest.TestCase):
    def test_decorator_registers_robot_style_name_and_recommendation(self):
        registry = KeywordRegistry()

        @keyword("Click Element")
        def click_element(locator: str):
            return locator

        registry.register_function(click_element)

        self.assertIs(registry.get("click_element").callable, click_element)
        self.assertIs(registry.get("Click Element").callable, click_element)
        with self.assertRaisesRegex(ValueError, "Did you mean: Click Element"):
            registry.get("Clik Element")

    def test_library_discovers_public_methods_and_skips_not_keyword(self):
        @library
        class DemoLibrary:
            def visible_keyword(self):
                return "ok"

            @not_keyword
            def helper(self):
                return "hidden"

            def _private(self):
                return "hidden"

        registry = KeywordRegistry()
        registry.register_library(DemoLibrary())

        self.assertEqual(registry.get("Visible Keyword").name, "Visible Keyword")
        with self.assertRaisesRegex(ValueError, "Unknown keyword 'Helper'"):
            registry.get("Helper")

    def test_duplicate_normalized_keyword_is_rejected(self):
        registry = KeywordRegistry()

        def first():
            return None

        def second():
            return None

        registry.register_function(first, name="Wait Visible")
        with self.assertRaisesRegex(ValueError, "Duplicate keyword"):
            registry.register_function(second, name="wait_visible")


if __name__ == "__main__":
    unittest.main()
