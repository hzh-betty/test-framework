from __future__ import annotations

from datetime import timedelta
import re


_TIMER_RE = re.compile(r"^([+-])?(\d+:)?(\d+):(\d+)(\.\d+)?$")


def parse_time(value: timedelta | int | float | str) -> float:
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"Invalid time value '{value}'.")

    raw = value.strip()
    if not raw:
        raise ValueError("Invalid time value ''.")
    numeric = _parse_number(raw)
    if numeric is not None:
        return numeric
    timer = _parse_timer(raw)
    if timer is not None:
        return timer
    unit_value = _parse_unit_time(raw)
    if unit_value is not None:
        return unit_value
    raise ValueError(f"Invalid time value '{value}'.")


def parse_positive_timeout(value: timedelta | int | float | str) -> float:
    timeout = parse_time(value)
    if timeout <= 0:
        raise ValueError(f"Timeout value '{value}' must be positive.")
    return timeout


def _parse_number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _parse_timer(value: str) -> float | None:
    match = _TIMER_RE.match(value)
    if not match:
        return None
    prefix, hours, minutes, seconds, millis = match.groups()
    total = float(minutes) * 60 + float(seconds)
    if hours:
        total += float(hours[:-1]) * 60 * 60
    if millis:
        total += float(millis)
    return -total if prefix == "-" else total


def _parse_unit_time(value: str) -> float | None:
    normalized = value.casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    pattern = re.compile(
        r"(?P<number>[+-]?\d+(?:\.\d+)?)\s*"
        r"(?P<unit>milliseconds?|millisec(?:ond)?s?|msecs?|ms|"
        r"seconds?|secs?|s|minutes?|mins?|min|m|hours?|h|days?|d|weeks?|w)"
    )
    position = 0
    total = 0.0
    matched = False
    for match in pattern.finditer(normalized):
        if normalized[position : match.start()].strip():
            return None
        matched = True
        number = float(match.group("number"))
        unit = match.group("unit")
        total += number * _unit_multiplier(unit)
        position = match.end()
    if not matched or normalized[position:].strip():
        return None
    return total


def _unit_multiplier(unit: str) -> float:
    if unit in {"millisecond", "milliseconds", "millisec", "millisecs", "msec", "msecs", "ms"}:
        return 0.001
    if unit in {"second", "seconds", "sec", "secs", "s"}:
        return 1.0
    if unit in {"minute", "minutes", "min", "mins", "m"}:
        return 60.0
    if unit in {"hour", "hours", "h"}:
        return 60.0 * 60.0
    if unit in {"day", "days", "d"}:
        return 60.0 * 60.0 * 24.0
    if unit in {"week", "weeks", "w"}:
        return 60.0 * 60.0 * 24.0 * 7.0
    raise ValueError(f"Unsupported time unit '{unit}'.")
