"""变量插值工具。

DSL 和运行配置都使用 ``${NAME}`` 语法。这里把递归替换逻辑集中起来，
避免加载器、执行器和配置处理各自实现一份相似代码。
"""

from __future__ import annotations

import re
from copy import deepcopy

from webtest_core.dsl.models import Scalar
from webtest_core.dsl.errors import DslValidationError


VARIABLE_PATTERN = re.compile(r"\$\{([^{}]+)\}")


def interpolate(value: object, variables: dict[str, Scalar], *, _stack: tuple[str, ...] = ()) -> object:
    """替换字符串、列表、字典中的 ``${name}`` 占位符。"""

    if isinstance(value, str):
        def lookup(match):
            name = match.group(1)
            if name not in variables:
                raise DslValidationError(f"Undefined variable: {name}")
            if name in _stack:
                raise DslValidationError("Variable cycle: " + " -> ".join((*_stack, name)))
            return interpolate(deepcopy(variables[name]), variables, _stack=(*_stack, name))

        match = VARIABLE_PATTERN.fullmatch(value)
        if match:
            return lookup(match)
        return VARIABLE_PATTERN.sub(lambda match: str(lookup(match)), value)
    if isinstance(value, list):
        return [interpolate(item, variables, _stack=_stack) for item in value]
    if isinstance(value, dict):
        return {key: interpolate(item, variables, _stack=_stack) for key, item in value.items()}
    return value
