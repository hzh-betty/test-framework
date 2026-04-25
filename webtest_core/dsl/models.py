"""YAML DSL 和运行配置的数据模型。

这些模型是框架入口处的“数据契约”。用户写的 YAML 会先被 Pydantic
转换成这些对象，执行器后续只处理类型明确、默认值完整的数据。
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


Scalar: TypeAlias = JsonValue


class StepSpec(BaseModel):
    """一个可执行步骤，对应一次关键字调用。"""

    model_config = ConfigDict(extra="forbid")

    keyword: str
    args: list[Scalar] = Field(default_factory=list)
    kwargs: dict[str, Scalar] = Field(default_factory=dict)
    timeout: str | int | float | None = None
    retry: int = 0
    continue_on_failure: bool = False

    @field_validator("keyword")
    @classmethod
    def keyword_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("keyword must not be blank")
        return value.strip()

    @field_validator("retry")
    @classmethod
    def retry_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("retry must be greater than or equal to 0")
        return value


class CaseSpec(BaseModel):
    """一个测试用例，以及用于筛选和统计的治理元数据。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    setup: list[StepSpec] = Field(default_factory=list)
    steps: list[StepSpec] = Field(default_factory=list)
    teardown: list[StepSpec] = Field(default_factory=list)
    variables: dict[str, Scalar] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    module: str | None = None
    type: str | None = None
    priority: str | None = None
    owner: str | None = None
    retry: int = 0
    continue_on_failure: bool = False

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("case name must not be blank")
        return value.strip()

    @field_validator("retry")
    @classmethod
    def retry_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("retry must be greater than or equal to 0")
        return value


class SuiteSpec(BaseModel):
    """顶层测试套件模型，执行器只接受这个结构。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    variables: dict[str, Scalar] = Field(default_factory=dict)
    setup: list[StepSpec] = Field(default_factory=list)
    cases: list[CaseSpec] = Field(default_factory=list)
    teardown: list[StepSpec] = Field(default_factory=list)
    keywords: dict[str, list[StepSpec]] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("suite name must not be blank")
        return value.strip()


class TimeoutConfig(BaseModel):
    """浏览器等待时间配置。"""

    implicit_wait: int = 10
    explicit_wait: int = 10


class SmtpConfig(BaseModel):
    """邮件通知所需的 SMTP 配置。"""

    host: str
    port: int
    username: str
    password: str
    sender: str
    receivers: list[str]


class NotificationConfig(BaseModel):
    """一个通知渠道的运行配置。"""

    type: Literal["email", "dingtalk", "webhook", "wechat", "feishu", "memory"]
    enabled: bool = True
    trigger: Literal["always", "on_failure", "on_success"] = "always"
    retries: int = 0
    webhook: str | None = None
    smtp: SmtpConfig | None = None


class NotificationsConfig(BaseModel):
    channels: list[NotificationConfig] = Field(default_factory=list)


class DeployConfig(BaseModel):
    commands: list[str] = Field(default_factory=list)


class PipelineConfig(BaseModel):
    deploy: DeployConfig = Field(default_factory=DeployConfig)


class RuntimeConfig(BaseModel):
    """CLI 在构造执行器前读取的运行配置。"""

    browser: Literal["chrome", "firefox", "edge"] = "chrome"
    headless: bool = False
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)
    logging: dict[str, Scalar] = Field(default_factory=dict)
    reports: dict[str, Scalar] = Field(default_factory=dict)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
