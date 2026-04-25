import unittest

from framework.parser.structured_payload import build_suite_from_mapping


class TestStructuredPayload(unittest.TestCase):
    def test_non_string_mapping_key_raises_value_error(self):
        payload = {
            "name": "SmokeSuite",
            "cases": [
                {
                    "name": "Login",
