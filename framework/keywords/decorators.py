from __future__ import annotations

from collections.abc import Callable


def keyword(name: str | None = None) -> Callable:
    def _decorate(func: Callable) -> Callable:
        setattr(func, "__keyword_name__", name or _humanize_name(func.__name__))
        setattr(func, "__keyword_enabled__", True)
        return func

    return _decorate


def not_keyword(func: Callable) -> Callable:
    setattr(func, "__not_keyword__", True)
    return func


def library(cls):
    setattr(cls, "__keyword_library__", True)
    return cls


def _humanize_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.strip("_").split("_") if part)
