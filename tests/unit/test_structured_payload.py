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
                        {"action": "open", "target": "https://example.test", 1: "boom"},
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
                    "steps": [{"action": "open", "target": "https://example.test"}],
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
            "setup": [{"action": "open", "target": "https://example.test/login"}],
            "teardown": [{"action": "screenshot", "target": "artifacts/suite-end.png"}],
            "cases": [
                {
                    "name": "Login",
                    "variables": {"username": "demo"},
                    "retry": 2,
                    "continue_on_failure": True,
                    "setup": [{"action": "wait_visible", "target": "id=username"}],
                    "teardown": [
                        {"action": "screenshot", "target": "artifacts/case-end.png"}
                    ],
                    "steps": [
                        {"action": "open", "target": "https://example.test/login"},
                        {
                            "action": "click",
                            "target": "id=submit",
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
                    "steps": [{"action": "open", "target": "https://example.test"}],
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
                            "action": "open",
                            "target": "https://example.test",
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
                            "action": "open",
                            "target": "https://example.test",
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
                    {"action": "open", "target": "https://example.test/login"},
                ],
                "login-flow": [
                    {"call": "open-login"},
                    {"action": "click", "target": "id=submit"},
                ],
            },
            "cases": [
                {
                    "name": "Login",
                    "steps": [{"call": "login-flow"}],
                }
            ],
        }

        suite = build_suite_from_mapping(payload, "inline")

        self.assertEqual(suite.keywords["open-login"][0].action, "open")
        self.assertEqual(suite.keywords["login-flow"][0].action, "call")
        self.assertEqual(suite.keywords["login-flow"][0].target, "open-login")
        self.assertEqual(suite.cases[0].steps[0].action, "call")
        self.assertEqual(suite.cases[0].steps[0].target, "login-flow")

    def test_build_suite_from_mapping_rejects_mixed_call_and_action_step(self):
        payload = {
            "name": "SmokeSuite",
            "cases": [
                {
                    "name": "Login",
                    "steps": [
                        {
                            "call": "login-flow",
                            "action": "open",
                            "target": "https://example.test/login",
                        }
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            r"inline \$\.cases\[0\]\.steps\[0\]\.call: cannot be combined with action/target/value",
        ):
            build_suite_from_mapping(payload, "inline")


if __name__ == "__main__":
    unittest.main()
