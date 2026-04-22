import unittest

from framework.parser.structured_payload import build_suite_from_mapping


class TestStructuredPayload(unittest.TestCase):
    def test_non_string_mapping_key_raises_value_error(self):
        payload = {
            "name": "SmokeSuite",
            "cases": [
                {
                    "name": "Login",
                    "steps": [
                        {"keyword": "Open", "args": ["https://example.test"], 1: "boom"},
                    ],
                }
            ],
        }

        with self.assertRaises(ValueError):
            build_suite_from_mapping(payload, "inline")

    def test_unknown_key_detection_remains_deterministic(self):
        payload = {
            "name": "SmokeSuite",
            "cases": [
                {
                    "name": "Login",
                    "steps": [{"keyword": "Open", "args": ["https://example.test"]}],
                    "zeta": "1",
                    "alpha": "2",
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, r"inline \$\.cases\[0\]\.alpha: unknown key"):
            build_suite_from_mapping(payload, "inline")

    def test_build_suite_from_mapping_supports_extended_fields(self):
        payload = {
            "name": "SmokeSuite",
            "variables": {"base_url": "https://example.test"},
            "setup": [{"keyword": "Open", "args": ["https://example.test/login"]}],
            "teardown": [{"keyword": "Screenshot", "args": ["artifacts/suite-end.png"]}],
            "cases": [
                {
                    "name": "Login",
                    "variables": {"username": "demo"},
                    "retry": 2,
                    "continue_on_failure": True,
                    "setup": [{"keyword": "Wait Visible", "args": ["id=username"]}],
                    "teardown": [
                        {"keyword": "Screenshot", "args": ["artifacts/case-end.png"]}
                    ],
                    "steps": [
                        {"keyword": "Open", "args": ["https://example.test/login"]},
                        {
                            "keyword": "Click",
                            "args": ["id=submit"],
                            "retry": 3,
                            "continue_on_failure": True,
                        },
                    ],
                }
            ],
        }

        suite = build_suite_from_mapping(payload, "inline")

        self.assertEqual(suite.variables["base_url"], "https://example.test")
        self.assertEqual(suite.setup[0].action, "open")
        self.assertEqual(suite.teardown[0].action, "screenshot")
        self.assertEqual(suite.cases[0].variables["username"], "demo")
        self.assertEqual(suite.cases[0].retry, 2)
        self.assertTrue(suite.cases[0].continue_on_failure)
        self.assertEqual(suite.cases[0].steps[1].retry, 3)
        self.assertTrue(suite.cases[0].steps[1].continue_on_failure)

    def test_build_suite_from_mapping_rejects_invalid_retry_type(self):
        payload = {
            "name": "SmokeSuite",
            "cases": [
                {
                    "name": "Login",
                    "retry": "3",
                    "steps": [{"keyword": "Open", "args": ["https://example.test"]}],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError, r"inline \$\.cases\[0\]\.retry: expected an integer"
        ):
            build_suite_from_mapping(payload, "inline")

    def test_build_suite_from_mapping_rejects_negative_retry_values(self):
        payload = {
            "name": "SmokeSuite",
            "cases": [
                {
                    "name": "Login",
                    "retry": -1,
                    "steps": [
                        {
                            "keyword": "Open",
                            "args": ["https://example.test"],
                            "retry": -2,
                        }
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            r"inline \$\.cases\[0\]\.retry: expected a non-negative integer",
        ):
            build_suite_from_mapping(payload, "inline")

    def test_build_suite_from_mapping_rejects_invalid_continue_on_failure_type(self):
        payload = {
            "name": "SmokeSuite",
            "cases": [
                {
                    "name": "Login",
                    "steps": [
                        {
                            "keyword": "Open",
                            "args": ["https://example.test"],
                            "continue_on_failure": "true",
                        }
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            r"inline \$\.cases\[0\]\.steps\[0\]\.continue_on_failure: expected a boolean",
        ):
            build_suite_from_mapping(payload, "inline")

    def test_build_suite_from_mapping_parses_keywords_and_call_shorthand(self):
        payload = {
            "name": "SmokeSuite",
            "keywords": {
                "open-login": [
                    {"keyword": "Open", "args": ["https://example.test/login"]},
                ],
                "login-flow": [
                    {"keyword": "open-login"},
                    {"keyword": "Click", "args": ["id=submit"]},
                ],
            },
            "cases": [
                {
                    "name": "Login",
                    "steps": [{"keyword": "login-flow"}],
                }
            ],
        }

        suite = build_suite_from_mapping(payload, "inline")

        self.assertEqual(suite.keywords["open-login"][0].keyword, "Open")
        self.assertEqual(suite.keywords["login-flow"][0].keyword, "open-login")
        self.assertEqual(suite.cases[0].steps[0].keyword, "login-flow")

    def test_build_suite_from_mapping_rejects_removed_call_shorthand(self):
        payload = {
            "name": "SmokeSuite",
            "cases": [
                {
                    "name": "Login",
                    "steps": [
                        {
                            "call": "login-flow",
                        }
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            r"inline \$\.cases\[0\]\.steps\[0\]\.call: unknown key",
        ):
            build_suite_from_mapping(payload, "inline")


if __name__ == "__main__":
    unittest.main()
