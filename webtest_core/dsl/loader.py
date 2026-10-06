"""YAML 套件和运行配置加载器。

加载器负责 I/O、环境变量展开和 Pydantic 错误格式化。执行器不直接读取
文件，这样测试时可以直接构造 ``SuiteSpec``，也便于以后接入其他来源。
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from webtest_core.dsl.errors import DslValidationError
from webtest_core.dsl.models import RuntimeConfig, SuiteSpec
from webtest_core.dsl.variables import VARIABLE_PATTERN


_BOOL_ADAPTER = TypeAdapter(bool)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def __init__(self, stream):
        super().__init__(stream)
        self._checked_mappings = set()

    def flatten_mapping(self, node):
        # 检查原始声明，允许合并键引入的默认值被显式键覆盖。
        if node not in self._checked_mappings:
            self._checked_mappings.add(node)
            keys = {}
            merge_mark = None
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    first_mark = merge_mark
                    merge_mark = key_node.start_mark
                else:
                    if key_node.tag == "tag:yaml.org,2002:value":
                        key_node.tag = "tag:yaml.org,2002:str"
                    key = self.construct_object(key_node)
                    try:
                        first_mark = keys.get(key)
                        keys[key] = key_node.start_mark
                    except TypeError as exc:
                        raise yaml.constructor.ConstructorError(
                            "while constructing a mapping", node.start_mark,
                            "found unhashable key", key_node.start_mark,
                        ) from exc
                if first_mark is not None:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", first_mark,
                        "found duplicate key", key_node.start_mark,
                    )
        super().flatten_mapping(node)


def load_suite(path: str | Path) -> SuiteSpec:
    """加载 YAML 测试套件并转换为 ``SuiteSpec``。"""

    source = Path(path)
    if source.suffix.lower() not in {".yaml", ".yml"}:
        raise DslValidationError("Only YAML DSL files are supported.")
    payload = _load_yaml_mapping(source)
    if "suite" not in payload:
        raise DslValidationError("suite root key is required.")
    if set(payload) != {"suite"}:
        raise DslValidationError("Only the suite root key is accepted.")
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
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (yaml.YAMLError, OSError) as exc:
        raise DslValidationError(f"Invalid YAML {path}: {exc}") from exc
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise DslValidationError("YAML document must be a mapping.")
    return payload


def _expand_env(value: object, location: str = "config", required: bool = True) -> object:
    if isinstance(value, str):
        def replace(match):
            name = match.group(1)
            if name not in os.environ and required:
                raise DslValidationError(f"{location}: Missing environment variable {name}")
            return os.environ.get(name, "")
        return VARIABLE_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_expand_env(item, f"{location}.{index}", required) for index, item in enumerate(value)]
    if isinstance(value, dict):
        if location.rsplit(".", 1)[0] == "config.notifications.channels" and "enabled" in value:
            enabled = _expand_env(value["enabled"], f"{location}.enabled", required)
            try:
                enabled = _BOOL_ADAPTER.validate_python(enabled)
            except ValidationError as exc:
                raise DslValidationError(_format_validation_error(exc, prefix=f"{location}.enabled")) from exc
            value = {**value, "enabled": enabled}
            if not enabled:
                required = False
        return {key: _expand_env(item, f"{location}.{key}", required) for key, item in value.items()}
    return value


def _format_validation_error(exc: ValidationError, *, prefix: str) -> str:
    errors = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        location = f"{prefix}.{location}" if location else prefix
        errors.append(f"{location}: {error['msg']}")
    return "; ".join(errors)
