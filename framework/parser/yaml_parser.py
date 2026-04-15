from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from framework.dsl.models import SuiteSpec

from .structured_payload import build_suite_from_mapping


class YamlCaseParser:
    def parse(self, case_file: str | Path) -> SuiteSpec:
        path = Path(case_file)
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: invalid YAML syntax: {exc}") from exc

        if not isinstance(payload, Mapping):
            raise ValueError(f"{path} $: expected a mapping")

        return build_suite_from_mapping(payload, source=str(path))
