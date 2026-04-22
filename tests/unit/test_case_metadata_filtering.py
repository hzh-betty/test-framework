import tempfile
import unittest
from pathlib import Path

from framework.dsl.models import CaseSpec, SuiteSpec
from framework.executor.execution_control import select_cases
from framework.parser.json_parser import JsonCaseParser
from framework.parser.xml_parser import XmlCaseParser
from framework.parser.yaml_parser import YamlCaseParser


class TestCaseMetadataFiltering(unittest.TestCase):
    def test_yaml_json_and_xml_parse_case_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            yaml_file = root / "case.yaml"
            yaml_file.write_text(
                """
name: MetadataSuite
cases:
  - name: Login
    module: auth
    type: smoke
    priority: p0
    owner: alice
    tags: smoke,login
    steps:
      - keyword: Open
        args: [https://example.test]
""",
                encoding="utf-8",
            )
            json_file = root / "case.json"
            json_file.write_text(
                """
{
  "name": "MetadataSuite",
  "cases": [
    {
      "name": "Login",
      "module": "auth",
      "type": "smoke",
      "priority": "p0",
      "owner": "alice",
      "steps": [{"keyword": "Open", "args": ["https://example.test"]}]
    }
  ]
}
""",
                encoding="utf-8",
            )
            xml_file = root / "case.xml"
            xml_file.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<suite name="MetadataSuite">
  <case name="Login" module="auth" type="smoke" priority="p0" owner="alice">
    <step keyword="Open"><arg value="https://example.test" /></step>
  </case>
</suite>
""",
                encoding="utf-8",
            )

            suites = [
                YamlCaseParser().parse(yaml_file),
                JsonCaseParser().parse(json_file),
                XmlCaseParser().parse(xml_file),
            ]

        for suite in suites:
            case = suite.cases[0]
            self.assertEqual(case.module, "auth")
            self.assertEqual(case.type, "smoke")
            self.assertEqual(case.priority, "p0")
            self.assertEqual(case.owner, "alice")

    def test_structured_parser_rejects_non_string_and_empty_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bad_type = root / "bad_type.yaml"
            bad_type.write_text(
                """
name: MetadataSuite
cases:
  - name: Login
    module: 123
    steps: []
""",
                encoding="utf-8",
            )
            bad_empty = root / "bad_empty.yaml"
            bad_empty.write_text(
                """
name: MetadataSuite
cases:
  - name: Login
    owner: " "
    steps: []
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"module: expected a string"):
                YamlCaseParser().parse(bad_type)
            with self.assertRaisesRegex(ValueError, r"owner: expected a non-empty string"):
                YamlCaseParser().parse(bad_empty)

    def test_select_cases_combines_metadata_filters_with_tags_and_allowed_names(self):
        suite = SuiteSpec(
            name="MetadataSuite",
            cases=[
                CaseSpec(
                    name="Login",
                    tags=["smoke"],
                    module="auth",
                    type="ui",
                    priority="p0",
                    owner="alice",
                ),
                CaseSpec(
                    name="Checkout",
                    tags=["smoke", "flaky"],
                    module="order",
                    type="ui",
                    priority="p1",
                    owner="bob",
                ),
                CaseSpec(
                    name="Api",
                    tags=["regression"],
                    module="auth",
                    type="api",
                    priority="p0",
                    owner="alice",
                ),
            ],
        )

        selected = select_cases(
            suite.cases,
            include_expr="smoke OR regression",
            exclude_expr="flaky",
            allowed_case_names={"Login", "Checkout", "Api"},
            modules={"auth"},
            case_types={"ui"},
            priorities={"p0"},
            owners={"alice"},
        )

        self.assertEqual([case.name for case in selected], ["Login"])


if __name__ == "__main__":
    unittest.main()
