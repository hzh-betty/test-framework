"""运行时公共 API。

该文件只导出执行器、筛选函数和结果模型；具体实现分散在更小的模块中。
"""

from webtest_core.runtime.executor import SuiteExecutor
from webtest_core.runtime.filtering import select_cases
from webtest_core.runtime.models import CaseResult, FailureType, StepResult, SuiteResult

__all__ = [
    "CaseResult",
    "FailureType",
    "StepResult",
    "SuiteExecutor",
    "SuiteResult",
    "select_cases",
]
