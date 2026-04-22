from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Callable, get_type_hints

from .converters import convert_argument


@dataclass(frozen=True)
class BoundKeywordArguments:
    args: tuple[object, ...]
    kwargs: dict[str, object]


def bind_keyword_arguments(
    func: Callable,
    args: list[object] | tuple[object, ...],
    kwargs: dict[str, object],
) -> BoundKeywordArguments:
    signature = inspect.signature(func)
    parameters = list(signature.parameters.values())
    positional: list[object] = []
    keyword_values: dict[str, object] = {}
    consumed_kwargs: set[str] = set()

    positional_parameters = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(args) > len(positional_parameters) and not any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters
    ):
        raise ValueError(f"too many positional arguments: expected {len(positional_parameters)}")

    type_hints = get_type_hints(func)
    for index, raw_value in enumerate(args):
        parameter = positional_parameters[index]
        if parameter.name in kwargs:
            raise ValueError(f"multiple values for argument: {parameter.name}")
        positional.append(_convert(raw_value, parameter, type_hints))

    for parameter in parameters[len(positional) :]:
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            for name, value in kwargs.items():
                if name not in consumed_kwargs:
                    keyword_values[name] = value
                    consumed_kwargs.add(name)
            continue
        if parameter.name in kwargs:
            value = _convert(kwargs[parameter.name], parameter, type_hints)
            if parameter.kind == inspect.Parameter.KEYWORD_ONLY:
                keyword_values[parameter.name] = value
            else:
                positional.append(value)
            consumed_kwargs.add(parameter.name)
        elif parameter.default is inspect.Parameter.empty:
            raise ValueError(f"missing required argument: {parameter.name}")
        elif parameter.kind == inspect.Parameter.KEYWORD_ONLY:
            keyword_values[parameter.name] = parameter.default
        else:
            positional.append(parameter.default)

    unknown = sorted(set(kwargs) - consumed_kwargs)
    if unknown:
        raise ValueError(f"unexpected keyword argument: {unknown[0]}")
    return BoundKeywordArguments(tuple(positional), keyword_values)


def _convert(
    value: object,
    parameter: inspect.Parameter,
    type_hints: dict[str, object],
) -> object:
    annotation = type_hints.get(parameter.name, parameter.annotation)
    if annotation is inspect.Parameter.empty:
        annotation = object
    try:
        return convert_argument(value, annotation, parameter.name)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
