"""用例筛选逻辑。

筛选独立于执行器，便于 CLI、重跑失败和未来的预览命令复用同一套规则。
"""

from __future__ import annotations

from webtest_core.dsl import CaseSpec


def select_cases(
    cases: list[CaseSpec],
    *,
    include_tag_expr: str | None = None,
    exclude_tag_expr: str | None = None,
    modules: set[str] | None = None,
    case_types: set[str] | None = None,
    priorities: set[str] | None = None,
    owners: set[str] | None = None,
    allowed_case_names: set[str] | None = None,
) -> list[CaseSpec]:
    selected = []
    for case in cases:
        if allowed_case_names is not None and case.name not in allowed_case_names:
            continue
        if modules is not None and (case.module or "") not in modules:
            continue
        if case_types is not None and (case.type or "") not in case_types:
            continue
        if priorities is not None and (case.priority or "") not in priorities:
            continue
        if owners is not None and (case.owner or "") not in owners:
            continue
        if include_tag_expr and not _matches_tag_expression(case.tags, include_tag_expr):
            continue
        if exclude_tag_expr and _matches_tag_expression(case.tags, exclude_tag_expr):
            continue
        selected.append(case)
    return selected


def _matches_tag_expression(tags: list[str], expression: str) -> bool:
    """执行一个小型 AND/OR/NOT 标签表达式。"""

    tokens = expression.replace("(", " ( ").replace(")", " ) ").split()
    tag_set = {tag.casefold() for tag in tags}
    python_tokens = []
    for token in tokens:
        lowered = token.casefold()
        if lowered in {"and", "or", "not", "(", ")"}:
            python_tokens.append(lowered)
        else:
            python_tokens.append(str(lowered in tag_set))
    try:
        return bool(eval(" ".join(python_tokens), {"__builtins__": {}}, {}))
    except Exception:
        return False
