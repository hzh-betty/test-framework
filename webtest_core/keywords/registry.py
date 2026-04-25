"""关键字注册与调用。

关键字本质上是普通 Python 函数。库对象的方法用 ``@keyword("Human Name")``
标记后，注册表会按规范化名称保存它们，让 DSL 可以使用 ``Type Text`` 这类
更适合测试人员阅读的名称。
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Callable


def normalize_keyword_name(name: str) -> str:
    """把关键字名规范化，便于宽松匹配空格、下划线和大小写。"""

    return re.sub(r"[\s_-]+", " ", name.strip().casefold())


def keyword(name: str):
    """把一个方法标记成可在 YAML DSL 中调用的关键字。"""

    def decorator(func: Callable):
        setattr(func, "__webtest_keyword__", name)
        return func

    return decorator


@dataclass(frozen=True)
class KeywordDefinition:
    name: str
    func: Callable


class KeywordRegistry:
    """保存关键字定义，并在调用前执行 Python 参数绑定。"""

    def __init__(self):
        self._keywords: dict[str, KeywordDefinition] = {}

    @classmethod
    def from_libraries(cls, libraries: list[object]):
        registry = cls()
        for library in libraries:
            registry.register_library(library)
        return registry

    def register(self, name: str, func: Callable) -> None:
        normalized = normalize_keyword_name(name)
        if normalized in self._keywords:
            raise ValueError(f"Duplicate keyword: {name}")
        self._keywords[normalized] = KeywordDefinition(name=name, func=func)

    def register_library(self, library: object) -> None:
        for _, member in inspect.getmembers(library, predicate=callable):
            name = getattr(member, "__webtest_keyword__", None)
            if name:
                self.register(name, member)

    def has(self, name: str) -> bool:
        return normalize_keyword_name(name) in self._keywords

    def get(self, name: str) -> KeywordDefinition:
        try:
            return self._keywords[normalize_keyword_name(name)]
        except KeyError as exc:
            raise KeyError(f"Unknown keyword: {name}") from exc

    def run(
        self,
        name: str,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
    ) -> object:
        definition = self.get(name)
        bound = inspect.signature(definition.func).bind(*(args or []), **(kwargs or {}))
        return definition.func(*bound.args, **bound.kwargs)
