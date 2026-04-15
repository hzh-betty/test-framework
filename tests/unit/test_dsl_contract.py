import unittest
from pathlib import Path

from framework.dsl.contract import DslFormat, detect_format
from framework.dsl.xml_schema import validate_xml_case_file


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dsl"


class TestDslContract(unittest.TestCase):
    def test_detect_format_by_extension(self):
        self.assertEqual(detect_format("suite/login.xml"), DslFormat.XML)
        self.assertEqual(detect_format("suite/login.yaml"), DslFormat.YAML)
        self.assertEqual(detect_format("suite/login.json"), DslFormat.JSON)

    def test_validate_xml_case_file_accepts_valid_file(self):
        case_file = FIXTURES / "valid_case.xml"
        self.assertTrue(validate_xml_case_file(case_file))

    def test_validate_xml_case_file_rejects_invalid_file(self):
        case_file = FIXTURES / "invalid_case.xml"
        with self.assertRaises(ValueError):
            validate_xml_case_file(case_file)

    def test_validate_xml_case_file_rejects_schema_violation(self):
        case_file = FIXTURES / "invalid_extra_attr.xml"
        with self.assertRaises(ValueError):
            validate_xml_case_file(case_file)


if __name__ == "__main__":
    unittest.main()
