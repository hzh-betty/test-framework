from __future__ import annotations

from collections.abc import Mapping

from framework.dsl.models import CaseSpec, Scalar, StepSpec, SuiteSpec

_ROOT_ALLOWED_KEYS = {"name", "cases", "setup", "teardown", "variables", "keywords"}
_CASE_ALLOWED_KEYS = {
    "name",
    "tags",
    "steps",
    "setup",
    "teardown",
    "variables",
    "module",
    "type",
    "priority",
    "owner",
    "retry",
    "continue_on_failure",
}
_STEP_ALLOWED_KEYS = {
    "keyword",
    "args",
    "kwargs",
    "timeout",
    "retry",
    "continue_on_failure",
}


def build_suite_from_mapping(payload: dict, source: str) -> SuiteSpec:
    root = _require_mapping(payload, source, "$")
    _require_allowed_keys(root, _ROOT_ALLOWED_KEYS, source, "$")

    suite_name = _require_string(root, "name", source, "$")
    setup = _build_steps_from_payload(root.get("setup", []), source, "$.setup")
    raw_cases = _require_list(root, "cases", source, "$")
    teardown = _build_steps_from_payload(root.get("teardown", []), source, "$.teardown")
    variables = _normalize_variables(root.get("variables", {}), source, "$.variables")
    keywords = _normalize_keywords(root.get("keywords", {}), source, "$.keywords")

    cases = [
        _build_case_from_mapping(case_payload, source, f"$.cases[{index}]")
        for index, case_payload in enumerate(raw_cases)
    ]
    return SuiteSpec(
        name=suite_name,
        setup=setup,
        cases=cases,
        teardown=teardown,
        variables=variables,
        keywords=keywords,
    )


def _build_case_from_mapping(payload: object, source: str, path: str) -> CaseSpec:
    case_data = _require_mapping(payload, source, path)
    _require_allowed_keys(case_data, _CASE_ALLOWED_KEYS, source, path)

    name = _require_string(case_data, "name", source, path)
    setup = _build_steps_from_payload(case_data.get("setup", []), source, f"{path}.setup")
    raw_steps = _require_list(case_data, "steps", source, path)
    teardown = _build_steps_from_payload(
        case_data.get("teardown", []), source, f"{path}.teardown"
    )
    variables = _normalize_variables(case_data.get("variables", {}), source, f"{path}.variables")
    tags = _normalize_tags(case_data.get("tags", []), source, f"{path}.tags")
    module = _require_optional_metadata(case_data, "module", source, path)
    case_type = _require_optional_metadata(case_data, "type", source, path)
    priority = _require_optional_metadata(case_data, "priority", source, path)
    owner = _require_optional_metadata(case_data, "owner", source, path)
    retry = _require_optional_integer(case_data, "retry", source, path)
    continue_on_failure = _require_optional_boolean(
        case_data,
        "continue_on_failure",
        source,
        path,
    )

    steps = _build_steps_from_payload(raw_steps, source, f"{path}.steps")
    return CaseSpec(
        name=name,
        setup=setup,
        steps=steps,
        teardown=teardown,
        variables=variables,
        tags=tags,
        module=module,
        type=case_type,
        priority=priority,
        owner=owner,
        retry=retry,
        continue_on_failure=continue_on_failure,
    )


def _build_step_from_mapping(payload: object, source: str, path: str) -> StepSpec:
    step_data = _require_mapping(payload, source, path)
    _require_allowed_keys(step_data, _STEP_ALLOWED_KEYS, source, path)

    keyword = _require_string(step_data, "keyword", source, path)
    args = _require_optional_scalar_list(step_data, "args", source, path)
    kwargs = _require_optional_scalar_mapping(step_data, "kwargs", source, path)
    timeout = _require_optional_scalar(step_data, "timeout", source, path)
    retry = _require_optional_integer(step_data, "retry", source, path)
    continue_on_failure = _require_optional_boolean(
        step_data,
        "continue_on_failure",
        source,
        path,
    )

    return StepSpec(
        keyword=keyword,
        args=args,
        kwargs=kwargs,
        timeout=timeout,
        retry=retry,
        continue_on_failure=continue_on_failure,
    )


def _build_steps_from_payload(payload: object, source: str, path: str) -> list[StepSpec]:
    if not isinstance(payload, list):
        _raise_value_error(source, path, "expected a list")
    return [
        _build_step_from_mapping(step_payload, source, f"{path}[{index}]")
        for index, step_payload in enumerate(payload)
    ]


def _normalize_tags(value: object, source: str, path: str) -> list[str]:
    if isinstance(value, str):
        raw_tags = value.split(",")
    elif isinstance(value, list):
        raw_tags = value
    else:
        _raise_value_error(source, path, "expected tags to be a list[str] or comma-separated string")

    normalized_tags: list[str] = []
    for index, tag in enumerate(raw_tags):
