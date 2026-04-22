from __future__ import annotations

from dataclasses import dataclass
import re

from .errors import LocatorError


LOCATOR_STRATEGIES = {
    "id": "id",
    "name": "name",
    "xpath": "xpath",
    "css": "css selector",
    "class": "class name",
    "tag": "tag name",
    "link": "link text",
    "partial_link": "partial link text",
}

SPECIAL_STRATEGIES = {"text", "partial_text", "testid", "data-testid"}
STRATEGY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z_-]*$")


@dataclass(frozen=True)
class Locator:
    by: str
    value: str
    raw: str

    @classmethod
    def parse(cls, raw_locator: str | None) -> "Locator":
        raw = "" if raw_locator is None else str(raw_locator)
        if not raw.strip():
            raise LocatorError("Invalid locator: empty locator.")
        if "=" not in raw:
            return cls(by=LOCATOR_STRATEGIES["css"], value=raw.strip(), raw=raw)

        strategy, value = raw.split("=", 1)
        if not STRATEGY_PATTERN.fullmatch(strategy.strip()):
            return cls(by=LOCATOR_STRATEGIES["css"], value=raw.strip(), raw=raw)
        normalized = strategy.strip().lower()
        locator_value = value.strip()
        if not locator_value:
            raise LocatorError(f"Invalid locator '{raw}': empty locator value.")
        if normalized in LOCATOR_STRATEGIES:
            return cls(by=LOCATOR_STRATEGIES[normalized], value=locator_value, raw=raw)
        if normalized == "text":
            return cls(
                by="xpath",
                value=f".//*[normalize-space(.) = {xpath_literal(locator_value)}]",
                raw=raw,
            )
        if normalized == "partial_text":
            return cls(
                by="xpath",
                value=f".//*[contains(normalize-space(.), {xpath_literal(locator_value)})]",
                raw=raw,
            )
        if normalized in {"testid", "data-testid"}:
            return cls(
                by=LOCATOR_STRATEGIES["css"],
                value=f'[data-testid="{css_string(locator_value)}"]',
                raw=raw,
            )
        known = ", ".join(sorted([*LOCATOR_STRATEGIES, *SPECIAL_STRATEGIES]))
        raise LocatorError(
            f"Unknown locator strategy '{strategy.strip()}' in '{raw}'. "
            f"Supported strategies: {known}."
        )


def css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    quoted = []
    for index, part in enumerate(parts):
        if part:
            quoted.append(f"'{part}'")
        if index != len(parts) - 1:
            quoted.append('"\'"')
    return f"concat({', '.join(quoted)})"
