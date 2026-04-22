from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StepSpec:
    action: str
    target: str | None = None
    value: str | None = None
    timeout: str | int | float | None = None
    retry: int | None = None
    continue_on_failure: bool = False


@dataclass(frozen=True)
class CaseSpec:
    name: str
    setup: list[StepSpec] = field(default_factory=list)
    steps: list[StepSpec] = field(default_factory=list)
    teardown: list[StepSpec] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    retry: int | None = None
    continue_on_failure: bool = False


@dataclass(frozen=True)
class SuiteSpec:
    name: str
    setup: list[StepSpec] = field(default_factory=list)
    cases: list[CaseSpec] = field(default_factory=list)
    teardown: list[StepSpec] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    keywords: dict[str, list[StepSpec]] = field(default_factory=dict)
