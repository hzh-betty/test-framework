from __future__ import annotations

from pathlib import Path
from typing import Protocol

from framework.dsl.models import SuiteSpec


class DslParser(Protocol):
    def parse(self, case_file: str | Path) -> SuiteSpec:
        """Parse an input DSL file into a suite specification."""
