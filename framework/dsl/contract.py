from __future__ import annotations

from enum import Enum
from pathlib import Path


class DslFormat(str, Enum):
    XML = "xml"
    YAML = "yaml"
    JSON = "json"


def detect_format(path: str | Path) -> DslFormat:
    suffix = Path(path).suffix.lower()
    if suffix == ".xml":
        return DslFormat.XML
    if suffix in (".yaml", ".yml"):
        return DslFormat.YAML
    if suffix == ".json":
        return DslFormat.JSON
    raise ValueError(f"Unsupported DSL file extension: '{suffix}'")
