from __future__ import annotations

from framework.dsl.models import CaseSpec
from framework.executor.tag_expression import compile_tag_expression


def select_cases(
    cases: list[CaseSpec],
    include_expr: str | None = None,
    exclude_expr: str | None = None,
    allowed_case_names: set[str] | None = None,
    modules: set[str] | None = None,
    case_types: set[str] | None = None,
    priorities: set[str] | None = None,
    owners: set[str] | None = None,
) -> list[CaseSpec]:
    include_fn = compile_tag_expression(include_expr) if include_expr is not None else None
    exclude_fn = compile_tag_expression(exclude_expr) if exclude_expr is not None else None

    selected_cases: list[CaseSpec] = []
    for case in cases:
        if allowed_case_names is not None and case.name not in allowed_case_names:
            continue
        if not _matches(case.module, modules):
            continue
        if not _matches(case.type, case_types):
            continue
        if not _matches(case.priority, priorities):
            continue
        if not _matches(case.owner, owners):
            continue

        case_tags = set(case.tags)
        if include_fn is not None and not include_fn(case_tags):
            continue
        if exclude_fn is not None and exclude_fn(case_tags):
            continue
        selected_cases.append(case)

    return selected_cases


def _matches(value: str | None, allowed_values: set[str] | None) -> bool:
    if not allowed_values:
        return True
    if value is None:
        return False
    return value.strip().lower() in allowed_values
