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


if __name__ == "__main__":
    unittest.main()
