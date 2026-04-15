from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from framework.dsl.models import SuiteSpec

from .structured_payload import build_suite_from_mapping


class JsonCaseParser:
    def parse(self, case_file: str | Path) -> SuiteSpec:
        path = Path(case_file)
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.loads(handle.read())
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON syntax: {exc}") from exc

        if not isinstance(payload, Mapping):
            raise ValueError("dsl $: expected a mapping")

        return build_suite_from_mapping(payload, source="dsl")
