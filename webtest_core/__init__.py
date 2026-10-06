"""现代化 WebTest 核心包。

新人只需要从 ``webtest_core`` 开始阅读：YAML 是唯一 DSL，``webtest`` 是唯一
CLI，运行时模型是唯一受支持的进程内 API。
"""

from importlib.metadata import version

__version__ = version("webtest-core")
