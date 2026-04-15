from __future__ import annotations

from pathlib import Path

from framework.dsl.contract import DslFormat, detect_format

from .base import DslParser
from .xml_parser import XmlCaseParser


def get_parser(case_file: str | Path) -> DslParser:
    dsl_format = detect_format(case_file)
    if dsl_format is DslFormat.XML:
        return XmlCaseParser()
    raise NotImplementedError(
        f"Parser for '{dsl_format.value}' is not implemented in V1. Use XML input."
    )


__all__ = ["DslParser", "XmlCaseParser", "get_parser"]
