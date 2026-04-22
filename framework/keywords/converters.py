from __future__ import annotations

from pathlib import Path
from typing import Any, Union, get_args, get_origin

from framework.core.time import parse_positive_timeout
from framework.selenium.errors import LocatorError
from framework.selenium.locators import Locator


def convert_argument(value: object, annotation: object, parameter_name: str) -> object:
    target = _resolve_annotation(annotation)
    if parameter_name == "timeout":
        return parse_positive_timeout(value)
    if target in (Any, object) or target is None:
        return value
    if target is str:
        return str(value)
    if target is int:
        if isinstance(value, bool):
            raise ValueError(f"Argument '{parameter_name}' must be an integer.")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Argument '{parameter_name}' must be an integer.") from exc
    if target is float:
        if isinstance(value, bool):
            raise ValueError(f"Argument '{parameter_name}' must be a number.")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Argument '{parameter_name}' must be a number.") from exc
    if target is bool:
        return _convert_bool(value, parameter_name)
    if target is Path:
        return Path(str(value))
    if target is Locator:
        try:
            return Locator.parse(str(value))
        except LocatorError as exc:
            raise ValueError(str(exc)) from exc
    return value


def _resolve_annotation(annotation: object) -> object:
    if annotation is None:
        return None
    if isinstance(annotation, str):
        return {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "Path": Path,
            "Locator": Locator,
        }.get(annotation, annotation)
    origin = get_origin(annotation)
    if origin in (Union, getattr(__import__("types"), "UnionType", object)):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return _resolve_annotation(args[0])
    return annotation


def _convert_bool(value: object, parameter_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    raise ValueError(f"Argument '{parameter_name}' must be a boolean.")
