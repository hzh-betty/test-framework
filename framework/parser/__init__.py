from __future__ import annotations

from pathlib import Path

from framework.dsl.contract import DslFormat, detect_format

from .base import DslParser
from .json_parser import JsonCaseParser
from .xml_parser import XmlCaseParser
from .yaml_parser import YamlCaseParser


def get_parser(case_file: str | Path) -> DslParser:
    dsl_format = detect_format(case_file)
    if dsl_format is DslFormat.XML:
        return XmlCaseParser()
    if dsl_format is DslFormat.YAML:
        return YamlCaseParser()
    if dsl_format is DslFormat.JSON:
        return JsonCaseParser()
    raise NotImplementedError(
        f"Parser for '{dsl_format.value}' is not implemented in V1. Supported formats: XML, YAML, JSON."
    )


__all__ = ["DslParser", "XmlCaseParser", "YamlCaseParser", "JsonCaseParser", "get_parser"]
