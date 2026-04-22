from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from framework.dsl.models import CaseSpec, Scalar, StepSpec, SuiteSpec
from framework.dsl.xml_schema import validate_xml_case_file


class XmlCaseParser:
    def parse(self, case_file: str | Path) -> SuiteSpec:
        path = Path(case_file)
        validate_xml_case_file(path)
        root = ET.parse(path).getroot()
        suite_setup = self._parse_steps_group(root.find("setup"))
        suite_teardown = self._parse_steps_group(root.find("teardown"))
        suite_variables = self._parse_variables(
            root.find("variables"),
            source=path,
            context="suite variables",
        )
        suite_keywords = self._parse_keywords(
            root.find("keywords"),
            source=path,
            context="suite keywords",
        )
        cases: list[CaseSpec] = []
        for case in root.findall("case"):
            case_name = case.attrib["name"]
            steps = [self._build_step(step) for step in case.findall("step")]
            tags = [
                tag.strip().lower()
                for tag in case.attrib.get("tags", "").split(",")
                if tag.strip()
            ]
            cases.append(
                CaseSpec(
                    name=case_name,
                    setup=self._parse_steps_group(case.find("setup")),
                    steps=steps,
                    teardown=self._parse_steps_group(case.find("teardown")),
                    variables=self._parse_variables(
                        case.find("variables"),
                        source=path,
                        context=f"case '{case_name}' variables",
                    ),
                    tags=tags,
                    module=self._parse_optional_metadata(case.attrib.get("module"), "module"),
                    type=self._parse_optional_metadata(case.attrib.get("type"), "type"),
                    priority=self._parse_optional_metadata(case.attrib.get("priority"), "priority"),
                    owner=self._parse_optional_metadata(case.attrib.get("owner"), "owner"),
                    retry=self._parse_optional_int(case.attrib.get("retry")),
                    continue_on_failure=self._parse_optional_bool(
                        case.attrib.get("continue_on_failure")
                    ),
                )
            )
        return SuiteSpec(
            name=root.attrib["name"],
            setup=suite_setup,
            cases=cases,
            teardown=suite_teardown,
            variables=suite_variables,
            keywords=suite_keywords,
        )

    def _parse_steps_group(self, element: ET.Element | None) -> list[StepSpec]:
        if element is None:
            return []
        return [self._build_step(step) for step in element.findall("step")]

    def _parse_variables(
        self,
        element: ET.Element | None,
        *,
        source: Path,
        context: str,
    ) -> dict[str, str]:
        if element is None:
            return {}
        variables: dict[str, str] = {}
        for index, var in enumerate(element.findall("var"), start=1):
            raw_name = var.attrib.get("name", "")
            name = raw_name.strip()
            if not name:
                raise ValueError(
                    f"{source.name}: empty variable name in {context} at var #{index}"
                )
            if name in variables:
                raise ValueError(
                    f"{source.name}: duplicate variable name '{name}' in {context} at var #{index}"
                )
            variables[name] = var.attrib["value"]
        return variables

    def _parse_keywords(
        self,
        element: ET.Element | None,
        *,
        source: Path,
        context: str,
    ) -> dict[str, list[StepSpec]]:
        if element is None:
            return {}
        keywords: dict[str, list[StepSpec]] = {}
        for index, keyword in enumerate(element.findall("keyword"), start=1):
            raw_name = keyword.attrib.get("name", "")
            name = raw_name.strip()
            if not name:
                raise ValueError(
                    f"{source.name}: empty keyword name in {context} at keyword #{index}"
                )
            if name in keywords:
                raise ValueError(
                    f"{source.name}: duplicate keyword name '{name}' in {context} at keyword #{index}"
                )
            keywords[name] = [self._build_step(step) for step in keyword.findall("step")]
        return keywords

    def _build_step(self, step: ET.Element) -> StepSpec:
        return StepSpec(
            keyword=step.attrib["keyword"],
            args=self._parse_args(step),
            kwargs=self._parse_kwargs(step),
            timeout=step.attrib.get("timeout"),
            retry=self._parse_optional_int(step.attrib.get("retry")),
            continue_on_failure=self._parse_optional_bool(
                step.attrib.get("continue_on_failure")
            ),
        )

    def _parse_args(self, step: ET.Element) -> list[Scalar]:
        return [self._parse_scalar(arg.attrib.get("value", arg.text or "")) for arg in step.findall("arg")]

    def _parse_kwargs(self, step: ET.Element) -> dict[str, Scalar]:
        kwargs: dict[str, Scalar] = {}
        for kwarg in step.findall("kwarg"):
            name = kwarg.attrib["name"].strip()
            if not name:
                raise ValueError("XML step kwarg name must not be empty.")
            if name in kwargs:
                raise ValueError(f"Duplicate XML step kwarg '{name}'.")
            kwargs[name] = self._parse_scalar(kwarg.attrib.get("value", kwarg.text or ""))
        return kwargs

    def _parse_scalar(self, value: str) -> Scalar:
        return value

    def _parse_optional_int(self, value: str | None) -> int | None:
        if value is None:
            return None
        return int(value)

    def _parse_optional_bool(self, value: str | None) -> bool:
        if value is None:
            return False
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
        raise ValueError(
            "Invalid boolean value for continue_on_failure: "
            f"'{value}'. Expected one of: true, false, 1, 0"
        )

    def _parse_optional_metadata(self, value: str | None, field: str) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError(f"XML case {field} must be a non-empty string.")
        return normalized
