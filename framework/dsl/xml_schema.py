from __future__ import annotations

from pathlib import Path

import xmlschema


SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "test_case.xsd"


def validate_xml_case_file(case_file: str | Path) -> bool:
    path = Path(case_file)
    if not path.exists():
        raise ValueError(f"DSL file does not exist: {path}")
    if not SCHEMA_PATH.exists():
        raise ValueError(f"XML schema file is missing: {SCHEMA_PATH}")

    schema = xmlschema.XMLSchema(str(SCHEMA_PATH))
    errors = list(schema.iter_errors(str(path)))
    if errors:
        raise ValueError(f"XML schema validation failed: {errors[0].reason}")
    return True
