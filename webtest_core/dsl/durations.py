"""DSL 和客户端共享的秒数转换。timeout 是受支持关键字的 I/O 等待时间。"""

import math
import re


def seconds(value: str | int | float | None, default: float = 10) -> float:
    if value is None:
        value = default
    if isinstance(value, bool):
        raise ValueError("timeout must be a finite non-negative duration")
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d*)?|\.\d+)\s*(ms|s|seconds?|min|minutes?)?\s*", value, re.I)
        if not match:
            raise ValueError(f"Invalid timeout: {value!r}")
        number, unit = match.groups()
        value = float(number) * {"ms": 0.001, "min": 60, "minute": 60, "minutes": 60}.get((unit or "s").lower(), 1)
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("timeout must be a finite non-negative duration")
    return result
