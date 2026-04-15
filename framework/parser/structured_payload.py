from __future__ import annotations

from collections.abc import Mapping

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec

_ROOT_ALLOWED_KEYS = {"name", "cases"}
_CASE_ALLOWED_KEYS = {"name", "tags", "steps"}
_STEP_ALLOWED_KEYS = {"action", "target", "value"}


def build_suite_from_mapping(payload: dict, source: str) -> SuiteSpec:
    root = _require_mapping(payload, source, "$")
    _require_allowed_keys(root, _ROOT_ALLOWED_KEYS, source, "$")

    suite_name = _require_string(root, "name", source, "$")
    raw_cases = _require_list(root, "cases", source, "$")

    cases = [
        _build_case_from_mapping(case_payload, source, f"$.cases[{index}]")
        for index, case_payload in enumerate(raw_cases)
    ]
    return SuiteSpec(name=suite_name, cases=cases)


def _build_case_from_mapping(payload: object, source: str, path: str) -> CaseSpec:
    case_data = _require_mapping(payload, source, path)
    _require_allowed_keys(case_data, _CASE_ALLOWED_KEYS, source, path)

    name = _require_string(case_data, "name", source, path)
    raw_steps = _require_list(case_data, "steps", source, path)
    tags = _normalize_tags(case_data.get("tags", []), source, f"{path}.tags")

    steps = [
        _build_step_from_mapping(step_payload, source, f"{path}.steps[{index}]")
        for index, step_payload in enumerate(raw_steps)
    ]
    return CaseSpec(name=name, steps=steps, tags=tags)


def _build_step_from_mapping(payload: object, source: str, path: str) -> StepSpec:
    step_data = _require_mapping(payload, source, path)
    _require_allowed_keys(step_data, _STEP_ALLOWED_KEYS, source, path)

    action = _require_string(step_data, "action", source, path)
    target = _require_string(step_data, "target", source, path)

    value: str | None = None
    if "value" in step_data:
        value = _require_string(step_data, "value", source, path)

    return StepSpec(action=action, target=target, value=value)


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


def _require_allowed_keys(
    data: Mapping[str, object], allowed_keys: set[str], source: str, path: str
) -> None:
    for key in sorted(data):
        if key not in allowed_keys:
            _raise_value_error(source, f"{path}.{key}", "unknown key")


def _raise_value_error(source: str, path: str, message: str) -> None:
    raise ValueError(f"{source} {path}: {message}")
