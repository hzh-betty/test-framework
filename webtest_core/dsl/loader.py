"""YAML 套件和运行配置加载器。

加载器负责 I/O、环境变量展开和 Pydantic 错误格式化。执行器不直接读取
文件，这样测试时可以直接构造 ``SuiteSpec``，也便于以后接入其他来源。
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from webtest_core.dsl.errors import DslValidationError
from webtest_core.dsl.models import RuntimeConfig, SuiteSpec
from webtest_core.dsl.variables import VARIABLE_PATTERN


def load_suite(path: str | Path) -> SuiteSpec:
    """加载 YAML 测试套件并转换为 ``SuiteSpec``。"""

    source = Path(path)
    if source.suffix.lower() not in {".yaml", ".yml"}:
        raise DslValidationError("Only YAML DSL files are supported.")
    payload = _load_yaml_mapping(source)
    if "suite" not in payload:
        raise DslValidationError("suite root key is required.")
    try:
        return SuiteSpec.model_validate(payload["suite"])
    except ValidationError as exc:
        raise DslValidationError(_format_validation_error(exc, prefix="suite")) from exc


def load_runtime_config(path: str | Path | None = None) -> RuntimeConfig:
    """加载运行配置；读取后先展开 ``${ENV_NAME}`` 环境变量。"""

    if path is None:
        return RuntimeConfig()
    payload = _expand_env(_load_yaml_mapping(Path(path)))
    try:
        return RuntimeConfig.model_validate(payload)
    except ValidationError as exc:
        raise DslValidationError(_format_validation_error(exc, prefix="config")) from exc


def _load_yaml_mapping(path: Path) -> dict:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise DslValidationError(f"Invalid YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise DslValidationError("YAML document must be a mapping.")
    return payload


def _expand_env(value: object) -> object:
    if isinstance(value, str):
        return VARIABLE_PATTERN.sub(lambda match: os.environ.get(match.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _format_validation_error(exc: ValidationError, *, prefix: str) -> str:
    errors = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        errors.append(f"{prefix}.{location}: {error['msg']}")
    return "; ".join(errors)
