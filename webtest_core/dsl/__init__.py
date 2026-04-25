"""DSL 公共 API。

该文件只负责导出稳定接口，具体实现分别在 ``models``、``loader`` 和
``variables`` 中。这样调用方导入路径不变，内部文件也更容易阅读。
"""

from webtest_core.dsl.errors import DslValidationError
from webtest_core.dsl.loader import load_runtime_config, load_suite
from webtest_core.dsl.models import (
    CaseSpec,
    DeployConfig,
    NotificationConfig,
    NotificationsConfig,
    PipelineConfig,
    RuntimeConfig,
    Scalar,
    SmtpConfig,
    StepSpec,
    SuiteSpec,
    TimeoutConfig,
)
from webtest_core.dsl.variables import VARIABLE_PATTERN, interpolate

__all__ = [
    "CaseSpec",
    "DeployConfig",
    "DslValidationError",
    "NotificationConfig",
    "NotificationsConfig",
    "PipelineConfig",
    "RuntimeConfig",
    "Scalar",
    "SmtpConfig",
    "StepSpec",
    "SuiteSpec",
    "TimeoutConfig",
    "VARIABLE_PATTERN",
    "interpolate",
    "load_runtime_config",
    "load_suite",
]
