"""YAML DSL 和运行配置的数据模型。

这些模型是框架入口处的“数据契约”。用户写的 YAML 会先被 Pydantic
转换成这些对象，执行器后续只处理类型明确、默认值完整的数据。
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator
from webtest_core.dsl.durations import seconds


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
    sensitive_args: list[int] = Field(default_factory=list)

    @field_validator("timeout", mode="before")
    @classmethod
    def valid_timeout(cls, value):
        if value is not None and not (isinstance(value, str) and "${" in value):
            seconds(value)
        return value

    @field_validator("sensitive_args")
    @classmethod
    def valid_sensitive_args(cls, value):
        if any(index < 0 for index in value):
            raise ValueError("sensitive_args indices must be non-negative")
        return list(dict.fromkeys(value))

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

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value):
        return list(dict.fromkeys(tag.strip().casefold() for tag in value if tag.strip()))

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

    @model_validator(mode="after")
    def unique_case_names(self):
        names = [case.name for case in self.cases]
        if len(names) != len(set(names)):
            raise ValueError("case names must be unique within a suite")
        return self

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("suite name must not be blank")
        return value.strip()


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeoutConfig(StrictConfig):
    """浏览器等待时间配置。"""

    implicit_wait: float = Field(default=0, ge=0, allow_inf_nan=False)
    explicit_wait: float = Field(default=10, ge=0, allow_inf_nan=False)


class SmtpConfig(StrictConfig):
    """邮件通知所需的 SMTP 配置。"""

    host: str
    port: int = Field(ge=1, le=65535)
    username: str
    password: str
    sender: str
    receivers: list[str] = Field(min_length=1)
    timeout: float = Field(default=10, gt=0, allow_inf_nan=False)


class NotificationConfig(StrictConfig):
    """一个通知渠道的运行配置。"""

    type: Literal["email", "dingtalk", "webhook", "feishu"]
    enabled: bool = True
    trigger: Literal["always", "on_failure", "on_success"] = "always"
    retries: int = Field(default=0, ge=0)
    webhook: str | None = None
    smtp: SmtpConfig | None = None

    @model_validator(mode="after")
    def validate_sender(self):
        if self.type == "email":
            if self.webhook is not None:
                raise ValueError("email does not accept webhook")
            if self.enabled and self.smtp is None:
                raise ValueError("enabled email requires smtp")
            if self.enabled and self.smtp and any(not value.strip() for value in (self.smtp.host, self.smtp.username, self.smtp.password, self.smtp.sender, *self.smtp.receivers)):
                raise ValueError("enabled email requires non-empty SMTP fields")
        else:
            if self.smtp is not None:
                raise ValueError(f"{self.type} does not accept smtp")
            if self.enabled and (not self.webhook or not self.webhook.startswith(("https://", "http://"))):
                raise ValueError("enabled webhook channel requires an HTTP(S) URL")
        return self


class NotificationsConfig(StrictConfig):
    channels: list[NotificationConfig] = Field(default_factory=list)


class DeployConfig(StrictConfig):
    commands: list[list[str]] = Field(default_factory=list)
    timeout: float = Field(default=300, gt=0, allow_inf_nan=False)

    @field_validator("commands")
    @classmethod
    def executable_commands(cls, value):
        if any(not command or not command[0].strip() for command in value):
            raise ValueError("deploy commands require a non-empty executable argument")
        return value


class PipelineConfig(StrictConfig):
    deploy: DeployConfig = Field(default_factory=DeployConfig)


class LoggingConfig(StrictConfig):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: str | None = None


class ReportConfig(StrictConfig):
    html: bool = False
    allure: bool = False


class RuntimeConfig(StrictConfig):
    """CLI 在构造执行器前读取的运行配置。"""

    browser: Literal["chrome", "firefox", "edge"] = "chrome"
    headless: bool = False
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    reports: ReportConfig = Field(default_factory=ReportConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
