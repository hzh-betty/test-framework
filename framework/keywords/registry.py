from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from difflib import get_close_matches
import inspect
import re


@dataclass(frozen=True)
class KeywordDefinition:
    name: str
    callable: Callable
    source: str


class KeywordRegistry:
    def __init__(self):
        self._keywords: dict[str, KeywordDefinition] = {}

    @property
    def keyword_names(self) -> tuple[str, ...]:
        return tuple(sorted(definition.name for definition in self._keywords.values()))

    def register_function(
        self,
        func: Callable,
        *,
        name: str | None = None,
        source: str | None = None,
    ) -> KeywordDefinition:
        keyword_name = name or getattr(func, "__keyword_name__", None) or _humanize_name(
            func.__name__
        )
        definition = KeywordDefinition(
            name=keyword_name,
            callable=func,
            source=source or _callable_source(func),
        )
        normalized = normalize_keyword_name(keyword_name)
        if normalized in self._keywords:
            existing = self._keywords[normalized]
            raise ValueError(
                f"Duplicate keyword '{keyword_name}' conflicts with '{existing.name}'."
            )
        self._keywords[normalized] = definition
        return definition

    def register_library(self, library: object) -> None:
        for name in dir(library):
            if name.startswith("_"):
                continue
            member = getattr(library, name)
            if not callable(member):
                continue
            if getattr(member, "__not_keyword__", False):
                continue
            explicit_name = getattr(member, "__keyword_name__", None)
            if not explicit_name and not getattr(library.__class__, "__keyword_library__", False):
                continue
            self.register_function(
                member,
                name=explicit_name or _humanize_name(name),
                source=f"{library.__class__.__module__}.{library.__class__.__name__}",
            )

    def get(self, name: str) -> KeywordDefinition:
        normalized = normalize_keyword_name(name)
        definition = self._keywords.get(normalized)
        if definition is not None:
            return definition
        matches = get_close_matches(normalized, self._keywords.keys(), n=3)
        if matches:
            suggestions = ", ".join(self._keywords[match].name for match in matches)
            raise ValueError(f"Unknown keyword '{name}'. Did you mean: {suggestions}?")
        supported = ", ".join(self.keyword_names)
        raise ValueError(f"Unknown keyword '{name}'. Supported keywords: {supported}.")


def normalize_keyword_name(name: str) -> str:
    normalized = re.sub(r"[_\-\s]+", " ", name.strip().casefold())
    return re.sub(r"\s+", " ", normalized).strip()


def _humanize_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.strip("_").split("_") if part)


def _callable_source(func: Callable) -> str:
    try:
        module = inspect.getmodule(func)
        module_name = module.__name__ if module else "__main__"
        return f"{module_name}.{func.__qualname__}"
    except Exception:
        return repr(func)
