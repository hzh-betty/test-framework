import unittest
import tempfile
from pathlib import Path

from framework.parser import get_parser
from framework.parser.json_parser import JsonCaseParser
from framework.parser.xml_parser import XmlCaseParser
from framework.parser.yaml_parser import YamlCaseParser


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dsl"


class TestParserLayer(unittest.TestCase):
    def test_get_parser_returns_xml_parser_for_xml_file(self):
        parser = get_parser("cases/login.xml")
        self.assertIsInstance(parser, XmlCaseParser)

    def test_get_parser_returns_yaml_parser_for_yaml_file(self):
        parser = get_parser("cases/login.yaml")
        self.assertIsInstance(parser, YamlCaseParser)

    def test_get_parser_returns_json_parser_for_json_file(self):
        parser = get_parser("cases/login.json")
        self.assertIsInstance(parser, JsonCaseParser)

    def test_xml_parser_parses_suite_case_and_steps(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case.xml")
        self.assertEqual(suite.name, "SmokeSuite")
        self.assertEqual(len(suite.cases), 1)
        self.assertEqual(suite.cases[0].name, "Login success")
        self.assertEqual(len(suite.cases[0].steps), 4)
        self.assertEqual(suite.cases[0].steps[0].action, "open")
        self.assertEqual(suite.cases[0].steps[0].target, "https://example.test/login")

    def test_yaml_parser_parses_suite_case_steps_and_tags(self):
        suite = YamlCaseParser().parse(FIXTURES / "valid_case.yaml")
        self.assertEqual(suite.name, "SmokeSuite")
        self.assertEqual(len(suite.cases), 1)
        case = suite.cases[0]
        self.assertEqual(case.name, "Login success")
        self.assertEqual(case.tags, ["smoke", "login"])
        self.assertEqual(len(case.steps), 4)
        self.assertEqual(case.steps[0].action, "open")
        self.assertEqual(case.steps[0].target, "https://example.test/login")

    def test_json_parser_parses_suite_case_steps_and_tags(self):
        suite = JsonCaseParser().parse(FIXTURES / "valid_case.json")
        self.assertEqual(suite.name, "SmokeSuite")
        self.assertEqual(len(suite.cases), 1)
        case = suite.cases[0]
        self.assertEqual(case.name, "Login success")
        self.assertEqual(case.tags, ["smoke", "login"])
        self.assertEqual(len(case.steps), 4)
        self.assertEqual(case.steps[0].action, "open")
        self.assertEqual(case.steps[0].target, "https://example.test/login")

    def test_xml_parser_parses_case_tags(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case_with_tags.xml")
        self.assertEqual(suite.cases[0].tags, ["smoke", "login"])

    def test_xml_parser_normalizes_case_tags_with_whitespace_and_empty_values(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case_with_tags_normalization.xml")
        self.assertEqual(suite.cases[0].tags, ["smoke", "login", "critical"])

    def test_yaml_parser_raises_on_unknown_field_fixture(self):
        with self.assertRaisesRegex(
            ValueError,
            r"invalid_unknown_field\.yaml \$\.cases\[0\]\.unexpected: unknown key",
        ):
            YamlCaseParser().parse(FIXTURES / "invalid_unknown_field.yaml")

    def test_json_parser_raises_on_type_mismatch_fixture(self):
        with self.assertRaisesRegex(
            ValueError,
            r"invalid_type\.json \$\.cases\[0\]\.steps\[0\]\.args\[0\]: expected a scalar",
        ):
            JsonCaseParser().parse(FIXTURES / "invalid_type.json")

    def test_yaml_parser_raises_on_negative_retry_fixture(self):
        with self.assertRaisesRegex(
            ValueError,
            r"invalid_negative_retry\.yaml \$\.cases\[0\]\.retry: expected a non-negative integer",
        ):
            YamlCaseParser().parse(FIXTURES / "invalid_negative_retry.yaml")

    def test_json_parser_raises_on_negative_retry_fixture(self):
        with self.assertRaisesRegex(
            ValueError,
            r"invalid_negative_retry\.json \$\.cases\[0\]\.retry: expected a non-negative integer",
        ):
            JsonCaseParser().parse(FIXTURES / "invalid_negative_retry.json")

    def test_yaml_parser_raises_on_syntax_error_with_file_context(self):
        case_file = FIXTURES / "invalid_syntax.yaml"
        with self.assertRaisesRegex(ValueError, r"invalid_syntax\.yaml"):
            YamlCaseParser().parse(case_file)
