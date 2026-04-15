import unittest
import importlib.util
from pathlib import Path

from framework.parser import get_parser
from framework.parser.xml_parser import XmlCaseParser
from framework.parser.yaml_parser import YamlCaseParser

if importlib.util.find_spec("framework.parser.json_parser") is None:
    JsonCaseParser = None
else:
    from framework.parser.json_parser import JsonCaseParser


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dsl"


class TestParserLayer(unittest.TestCase):
    def test_get_parser_returns_xml_parser_for_xml_file(self):
        parser = get_parser("cases/login.xml")
        self.assertIsInstance(parser, XmlCaseParser)

    def test_get_parser_returns_yaml_parser_for_yaml_file(self):
        parser = get_parser("cases/login.yaml")
        self.assertIsInstance(parser, YamlCaseParser)

    def test_get_parser_json_not_implemented_message_matches_task3_support(self):
        with self.assertRaisesRegex(
            NotImplementedError,
            r"Supported formats: XML, YAML\.$",
        ):
            get_parser("cases/login.json")

    def test_get_parser_returns_json_parser_for_json_file(self):
        if JsonCaseParser is None:
            self.skipTest("JsonCaseParser not available until Task4")
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
        if JsonCaseParser is None:
            self.skipTest("JsonCaseParser not available until Task4")
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
        with self.assertRaises(ValueError):
            YamlCaseParser().parse(FIXTURES / "invalid_unknown_field.yaml")

    def test_json_parser_raises_on_type_mismatch_fixture(self):
        if JsonCaseParser is None:
            self.skipTest("JsonCaseParser not available until Task4")
        with self.assertRaises(ValueError):
            JsonCaseParser().parse(FIXTURES / "invalid_type.json")

    def test_yaml_parser_raises_on_syntax_error_with_file_context(self):
        case_file = FIXTURES / "invalid_syntax.yaml"
        with self.assertRaisesRegex(ValueError, r"invalid_syntax\.yaml"):
            YamlCaseParser().parse(case_file)

    def test_yaml_parser_raises_when_root_is_not_mapping(self):
        case_file = FIXTURES / "invalid_root_sequence.yaml"
        with self.assertRaisesRegex(ValueError, r"dsl \$: expected a mapping"):
            YamlCaseParser().parse(case_file)

    def test_xml_parser_raises_on_invalid_xml(self):
        with self.assertRaises(ValueError):
            XmlCaseParser().parse(FIXTURES / "invalid_case.xml")

if __name__ == "__main__":
    unittest.main()
