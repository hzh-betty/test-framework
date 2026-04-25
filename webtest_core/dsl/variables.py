"""变量插值工具。

DSL 和运行配置都使用 ``${NAME}`` 语法。这里把递归替换逻辑集中起来，
避免加载器、执行器和配置处理各自实现一份相似代码。
"""

from __future__ import annotations

import re

from webtest_core.dsl.models import Scalar


VARIABLE_PATTERN = re.compile(r"\$\{([^{}]+)\}")


def interpolate(value: object, variables: dict[str, Scalar]) -> object:
    """替换字符串、列表、字典中的 ``${name}`` 占位符。"""

    if isinstance(value, str):
        return VARIABLE_PATTERN.sub(
            lambda match: str(variables.get(match.group(1), match.group(0))),
            value,
        )
    if isinstance(value, list):
        return [interpolate(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: interpolate(item, variables) for key, item in value.items()}
    return value
