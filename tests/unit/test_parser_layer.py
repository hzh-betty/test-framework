import unittest
from pathlib import Path

from framework.parser import get_parser
from framework.parser.xml_parser import XmlCaseParser


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dsl"


class TestParserLayer(unittest.TestCase):
    def test_get_parser_returns_xml_parser_for_xml_file(self):
        parser = get_parser("cases/login.xml")
        self.assertIsInstance(parser, XmlCaseParser)

    def test_xml_parser_parses_suite_case_and_steps(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case.xml")
        self.assertEqual(suite.name, "SmokeSuite")
        self.assertEqual(len(suite.cases), 1)
        self.assertEqual(suite.cases[0].name, "Login success")
        self.assertEqual(len(suite.cases[0].steps), 4)
        self.assertEqual(suite.cases[0].steps[0].action, "open")
        self.assertEqual(suite.cases[0].steps[0].target, "https://example.test/login")

    def test_xml_parser_parses_case_tags(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case_with_tags.xml")
        self.assertEqual(suite.cases[0].tags, ["smoke", "login"])

    def test_xml_parser_normalizes_case_tags_with_whitespace_and_empty_values(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case_with_tags_normalization.xml")
        self.assertEqual(suite.cases[0].tags, ["smoke", "login", "critical"])

    def test_xml_parser_raises_on_invalid_xml(self):
        with self.assertRaises(ValueError):
            XmlCaseParser().parse(FIXTURES / "invalid_case.xml")

    def test_get_parser_raises_for_unimplemented_yaml(self):
        with self.assertRaises(NotImplementedError):
            get_parser("cases/login.yaml")


if __name__ == "__main__":
    unittest.main()
