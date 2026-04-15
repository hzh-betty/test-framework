from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.dsl.xml_schema import validate_xml_case_file


class XmlCaseParser:
    def parse(self, case_file: str | Path) -> SuiteSpec:
        path = Path(case_file)
        validate_xml_case_file(path)
        root = ET.parse(path).getroot()
        cases: list[CaseSpec] = []
        for case in root.findall("case"):
            steps = [
                StepSpec(
                    action=step.attrib["action"],
                    target=step.attrib["target"],
                    value=step.attrib.get("value"),
                )
                for step in case.findall("step")
            ]
            tags = [
                tag.strip().lower()
                for tag in case.attrib.get("tags", "").split(",")
                if tag.strip()
            ]
            cases.append(CaseSpec(name=case.attrib["name"], steps=steps, tags=tags))
        return SuiteSpec(name=root.attrib["name"], cases=cases)
