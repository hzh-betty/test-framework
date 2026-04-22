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
            r"invalid_type\.json \$\.cases\[0\]\.steps\[0\]\.target: expected a string",
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

    def test_yaml_parser_raises_when_root_is_not_mapping(self):
        case_file = FIXTURES / "invalid_root_sequence.yaml"
        with self.assertRaisesRegex(
            ValueError, r"invalid_root_sequence\.yaml \$: expected a mapping"
        ):
            YamlCaseParser().parse(case_file)

    def test_xml_parser_raises_on_invalid_xml(self):
        with self.assertRaises(ValueError):
            XmlCaseParser().parse(FIXTURES / "invalid_case.xml")

    def test_xml_parser_raises_on_negative_retry_fixture(self):
        with self.assertRaisesRegex(
            ValueError,
            r"XML schema validation failed",
        ):
            XmlCaseParser().parse(FIXTURES / "invalid_negative_retry.xml")

    def test_xml_parser_raises_on_duplicate_variable_names(self):
        with self.assertRaisesRegex(
            ValueError,
            r"invalid_duplicate_variables\.xml: duplicate variable name 'base_url'",
        ):
            XmlCaseParser().parse(FIXTURES / "invalid_duplicate_variables.xml")

    def test_xml_parser_raises_on_duplicate_keyword_names(self):
        with self.assertRaisesRegex(
            ValueError,
            r"invalid_duplicate_keywords\.xml: duplicate keyword name 'login'",
        ):
            XmlCaseParser().parse(FIXTURES / "invalid_duplicate_keywords.xml")

    def test_xml_parser_raises_on_empty_variable_name(self):
        with self.assertRaisesRegex(
            ValueError,
            r"invalid_empty_variable_name\.xml: empty variable name",
        ):
            XmlCaseParser().parse(FIXTURES / "invalid_empty_variable_name.xml")

    def test_xml_parser_raises_on_empty_keyword_name(self):
        with self.assertRaisesRegex(
            ValueError,
            r"invalid_empty_keyword_name\.xml: empty keyword name",
        ):
            XmlCaseParser().parse(FIXTURES / "invalid_empty_keyword_name.xml")

    def test_yaml_parser_parses_extended_suite_case_and_step_fields(self):
        suite = YamlCaseParser().parse(FIXTURES / "valid_case_extended.yaml")

        self.assertEqual(suite.variables["base_url"], "https://example.test")
        self.assertEqual(suite.setup[0].action, "open")
        self.assertEqual(suite.teardown[0].action, "screenshot")

        case = suite.cases[0]
        self.assertEqual(case.variables["username"], "demo")
        self.assertEqual(case.retry, 2)
        self.assertTrue(case.continue_on_failure)
        self.assertEqual(case.setup[0].action, "wait_visible")
        self.assertEqual(case.teardown[0].action, "screenshot")
        self.assertEqual(case.steps[1].retry, 3)
        self.assertTrue(case.steps[1].continue_on_failure)

    def test_json_parser_parses_extended_suite_case_and_step_fields(self):
        suite = JsonCaseParser().parse(FIXTURES / "valid_case_extended.json")

        self.assertEqual(suite.variables["base_url"], "https://example.test")
        self.assertEqual(suite.setup[0].action, "open")
        self.assertEqual(suite.teardown[0].action, "screenshot")

        case = suite.cases[0]
        self.assertEqual(case.variables["username"], "demo")
        self.assertEqual(case.retry, 2)
        self.assertTrue(case.continue_on_failure)
        self.assertEqual(case.setup[0].action, "wait_visible")
        self.assertEqual(case.teardown[0].action, "screenshot")
        self.assertEqual(case.steps[1].retry, 3)
        self.assertTrue(case.steps[1].continue_on_failure)

    def test_xml_parser_parses_extended_suite_case_and_step_fields(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case_extended.xml")

        self.assertEqual(suite.variables["base_url"], "https://example.test")
        self.assertEqual(suite.setup[0].action, "open")
        self.assertEqual(suite.teardown[0].action, "screenshot")

        case = suite.cases[0]
        self.assertEqual(case.variables["username"], "demo")
        self.assertEqual(case.retry, 2)
        self.assertTrue(case.continue_on_failure)
        self.assertEqual(case.setup[0].action, "wait_visible")
        self.assertEqual(case.teardown[0].action, "screenshot")
        self.assertEqual(case.steps[1].retry, 3)
        self.assertTrue(case.steps[1].continue_on_failure)

    def test_xml_parser_parses_boolean_variants_for_case_and_step_continue_on_failure(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case_boolean_variants.xml")

        self.assertEqual(
            [case.continue_on_failure for case in suite.cases],
            [True, True, False, False],
        )
        self.assertEqual(
            [case.steps[0].continue_on_failure for case in suite.cases],
            [True, True, False, False],
        )

    def test_xml_parser_raises_clear_error_for_invalid_boolean_value(self):
        with self.assertRaisesRegex(
            ValueError,
            r"Invalid boolean value for continue_on_failure: 'maybe'.*true, false, 1, 0",
        ):
            XmlCaseParser()._parse_optional_bool("maybe")

    def test_yaml_parser_parses_keywords_and_call_steps(self):
        suite = YamlCaseParser().parse(FIXTURES / "valid_case_keywords.yaml")

        self.assertIn("login", suite.keywords)
        self.assertEqual(suite.keywords["submit-login"][0].action, "call")
        self.assertEqual(suite.keywords["submit-login"][0].target, "login")
        self.assertEqual(suite.cases[0].steps[0].action, "call")
        self.assertEqual(suite.cases[0].steps[0].target, "submit-login")

    def test_json_parser_parses_keywords_and_call_steps(self):
        suite = JsonCaseParser().parse(FIXTURES / "valid_case_keywords.json")

        self.assertIn("login", suite.keywords)
        self.assertEqual(suite.keywords["submit-login"][0].action, "call")
        self.assertEqual(suite.keywords["submit-login"][0].target, "login")
        self.assertEqual(suite.cases[0].steps[0].action, "call")
        self.assertEqual(suite.cases[0].steps[0].target, "submit-login")

    def test_xml_parser_parses_keywords_and_call_steps(self):
        suite = XmlCaseParser().parse(FIXTURES / "valid_case_keywords.xml")

        self.assertIn("login", suite.keywords)
        self.assertEqual(suite.keywords["submit-login"][0].action, "call")
        self.assertEqual(suite.keywords["submit-login"][0].target, "login")
        self.assertEqual(suite.cases[0].steps[0].action, "call")
        self.assertEqual(suite.cases[0].steps[0].target, "submit-login")

    def test_xml_parser_parses_timeout_and_optional_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            case_file = Path(tmpdir) / "timeout.xml"
            case_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="TimeoutSuite">
  <case name="Alert">
    <step action="accept_alert" timeout="500ms" />
  </case>
</suite>
""",
                encoding="utf-8",
            )

            suite = XmlCaseParser().parse(case_file)

        step = suite.cases[0].steps[0]
        self.assertEqual(step.action, "accept_alert")
        self.assertIsNone(step.target)
        self.assertEqual(step.timeout, "500ms")

    def test_yaml_parser_parses_timeout_and_optional_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            case_file = Path(tmpdir) / "timeout.yaml"
            case_file.write_text(
                """
name: TimeoutSuite
cases:
  - name: Alert
    steps:
      - action: accept_alert
        timeout: 2s
""",
                encoding="utf-8",
            )

            suite = YamlCaseParser().parse(case_file)

        step = suite.cases[0].steps[0]
        self.assertEqual(step.action, "accept_alert")
        self.assertIsNone(step.target)
        self.assertEqual(step.timeout, "2s")

if __name__ == "__main__":
    unittest.main()
