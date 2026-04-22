from __future__ import annotations

from collections.abc import Mapping

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec

_ROOT_ALLOWED_KEYS = {"name", "cases", "setup", "teardown", "variables", "keywords"}
_CASE_ALLOWED_KEYS = {
    "name",
    "tags",
    "steps",
    "setup",
    "teardown",
    "variables",
    "retry",
    "continue_on_failure",
}
_STEP_ALLOWED_KEYS = {
    "action",
    "target",
    "value",
    "timeout",
    "retry",
    "continue_on_failure",
    "call",
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
        retry=retry,
        continue_on_failure=continue_on_failure,
    )


def _build_step_from_mapping(payload: object, source: str, path: str) -> StepSpec:
    step_data = _require_mapping(payload, source, path)
    _require_allowed_keys(step_data, _STEP_ALLOWED_KEYS, source, path)

    if "call" in step_data:
        if any(key in step_data for key in ("action", "target", "value", "timeout")):
            _raise_value_error(
                source,
                f"{path}.call",
                "cannot be combined with action/target/value/timeout",
            )
        action = "call"
        target = _require_string(step_data, "call", source, path)
    else:
        action = _require_string(step_data, "action", source, path)
        target = _require_optional_string(step_data, "target", source, path)

    value: str | None = None
    if "call" in step_data and "value" in step_data:
        _raise_value_error(source, f"{path}.value", "is not supported for call steps")
    if "value" in step_data:
        value = _require_string(step_data, "value", source, path)
    timeout = _require_optional_scalar(step_data, "timeout", source, path)
    retry = _require_optional_integer(step_data, "retry", source, path)
    continue_on_failure = _require_optional_boolean(
        step_data,
        "continue_on_failure",
        source,
        path,
    )

    return StepSpec(
        action=action,
        target=target,
        value=value,
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
        if not isinstance(tag, str):
            _raise_value_error(source, f"{path}[{index}]", "expected a string")

        normalized = tag.strip().lower()
        if normalized:
            normalized_tags.append(normalized)

    return normalized_tags


def _normalize_variables(value: object, source: str, path: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        _raise_value_error(source, path, "expected a mapping")

    normalized: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            _raise_value_error(source, path, "expected mapping keys to be strings")
        if not isinstance(item, str):
            _raise_value_error(source, f"{path}.{key}", "expected a string")
        normalized[key] = item
    return normalized


def _normalize_keywords(value: object, source: str, path: str) -> dict[str, list[StepSpec]]:
    if not isinstance(value, Mapping):
        _raise_value_error(source, path, "expected a mapping")

    normalized: dict[str, list[StepSpec]] = {}
    for keyword_name, steps in value.items():
        if not isinstance(keyword_name, str) or not keyword_name.strip():
            _raise_value_error(source, path, "expected keyword names to be non-empty strings")
        normalized[keyword_name] = _build_steps_from_payload(
            steps,
            source,
            f"{path}.{keyword_name}",
        )
    return normalized


def _require_mapping(payload: object, source: str, path: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        _raise_value_error(source, path, "expected a mapping")
    return payload


def _require_list(data: Mapping[str, object], key: str, source: str, path: str) -> list[object]:
    if key not in data:
        _raise_value_error(source, f"{path}.{key}", "missing required key")

    value = data[key]
    if not isinstance(value, list):
        _raise_value_error(source, f"{path}.{key}", "expected a list")

    return value


def _require_string(data: Mapping[str, object], key: str, source: str, path: str) -> str:
    if key not in data:
        _raise_value_error(source, f"{path}.{key}", "missing required key")

    value = data[key]
    if not isinstance(value, str):
        _raise_value_error(source, f"{path}.{key}", "expected a string")

    return value


def _require_optional_string(
    data: Mapping[str, object], key: str, source: str, path: str
) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, str):
        _raise_value_error(source, f"{path}.{key}", "expected a string")
    return value


def _require_optional_scalar(
    data: Mapping[str, object], key: str, source: str, path: str
) -> str | int | float | None:
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        _raise_value_error(source, f"{path}.{key}", "expected a string or number")
    return value


def _require_optional_integer(
    data: Mapping[str, object], key: str, source: str, path: str
) -> int | None:
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        _raise_value_error(source, f"{path}.{key}", "expected an integer")
    if value < 0:
        _raise_value_error(source, f"{path}.{key}", "expected a non-negative integer")
    return value


def _require_optional_boolean(
    data: Mapping[str, object], key: str, source: str, path: str
) -> bool:
    if key not in data:
        return False
    value = data[key]
    if not isinstance(value, bool):
        _raise_value_error(source, f"{path}.{key}", "expected a boolean")
    return value


def _require_allowed_keys(
    data: Mapping[str, object], allowed_keys: set[str], source: str, path: str
) -> None:
    for key in data:
        if not isinstance(key, str):
            _raise_value_error(source, path, "expected mapping keys to be strings")

    for key in sorted(data):
        if key not in allowed_keys:
            _raise_value_error(source, f"{path}.{key}", "unknown key")


def _raise_value_error(source: str, path: str, message: str) -> None:
    raise ValueError(f"{source} {path}: {message}")
