from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StepSpec:
    action: str
    target: str
    value: str | None = None


@dataclass(frozen=True)
class CaseSpec:
    name: str
    steps: list[StepSpec] = field(default_factory=list)


@dataclass(frozen=True)
class SuiteSpec:
    name: str
    cases: list[CaseSpec] = field(default_factory=list)
