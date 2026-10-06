from pathlib import Path

import pytest
import yaml

from webtest_core.dsl import DslValidationError, RuntimeConfig, load_runtime_config, load_suite


@pytest.mark.parametrize("content", [
    "suite:\n  name: Duplicate\n  cases:\n    - name: case\n      steps: [{keyword: Fail}]\n      steps: [{keyword: Pass}]\n",
    "suite:\n  name: Duplicate\n  name: Overwritten\n",
    "suite:\n  name: Duplicate\n  variables: {first: 1, first: 2}\n",
])
def test_suite_rejects_duplicate_keys_with_location(tmp_path: Path, content):
    source = tmp_path / "duplicate.yaml"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(DslValidationError, match=r"duplicate key.*\n.*line \d+, column \d+"):
        load_suite(source)


def test_runtime_config_rejects_duplicate_keys(tmp_path):
    source = tmp_path / "config.yaml"
    source.write_text("headless: true\nheadless: false\n", encoding="utf-8")
    with pytest.raises(DslValidationError, match="duplicate key"):
        load_runtime_config(source)


def test_yaml_merge_defaults_allow_explicit_overrides_and_alias_reuse(tmp_path):
    source = tmp_path / "merge.yaml"
    source.write_text("""suite:
  name: Merge
  cases:
    - &defaults
      name: first
      steps: [{keyword: Pass}]
      variables: {count: 1}
    - <<: *defaults
      name: second
      variables: {count: 2}
    - <<: [*defaults, {name: fallback}]
      name: third
""", encoding="utf-8")
    suite = load_suite(source)
    assert [case.name for case in suite.cases] == ["first", "second", "third"]
    assert suite.cases[1].variables == {"count": 2}
    assert all(case.steps[0].keyword == "Pass" for case in suite.cases)


@pytest.mark.parametrize("variables", [
    "{<<: {count: 1, count: 2}}",
    "{<<: {count: 1}, <<: {other: 2}}",
    "{true: first, 1: second}",
])
def test_duplicate_keys_inside_merge_sources_are_rejected(tmp_path, variables):
    source = tmp_path / "merge.yaml"
    source.write_text(f"suite:\n  name: Merge\n  variables: {variables}\n", encoding="utf-8")
    with pytest.raises(DslValidationError, match="duplicate key"):
        load_suite(source)


def test_yaml_remains_safe(tmp_path):
    source = tmp_path / "unsafe.yaml"
    source.write_text("suite: !!python/object/apply:builtins.dict []", encoding="utf-8")
    with pytest.raises(DslValidationError, match="could not determine a constructor"):
        load_suite(source)


def test_yaml_value_key_keeps_safe_loader_semantics(tmp_path):
    source = tmp_path / "value.yaml"
    source.write_text("suite:\n  name: Value\n  variables: {=: value}\n", encoding="utf-8")
    assert load_suite(source).variables == {"=": "value"}


@pytest.mark.parametrize("enabled", [False, 0, 0.0, "0", "false", "FALSE", "no", "off", "n", "f"])
def test_disabled_channels_match_model_boolean_normalization(tmp_path, monkeypatch, enabled):
    monkeypatch.delenv("WEBTEST_MISSING_WEBHOOK", raising=False)
    source = tmp_path / "config.yaml"
    payload = {"notifications": {"channels": [{"type": "webhook", "enabled": enabled,
        "webhook": "${WEBTEST_MISSING_WEBHOOK}"}]}}
    source.write_text(yaml.safe_dump(payload), encoding="utf-8")
    expected = RuntimeConfig.model_validate({"notifications": {"channels": [{"type": "webhook", "enabled": enabled}]}})
    actual = load_runtime_config(source)
    assert actual.notifications.channels[0].enabled is expected.notifications.channels[0].enabled is False
    assert actual.notifications.channels[0].webhook == ""


@pytest.mark.parametrize("enabled", ["f", "n", "0"])
def test_disabled_channel_environment_values_use_model_boolean_rules(tmp_path, monkeypatch, enabled):
    monkeypatch.setenv("WEBTEST_ENABLED", enabled)
    monkeypatch.delenv("WEBTEST_MISSING_WEBHOOK", raising=False)
    source = tmp_path / "config.yaml"
    source.write_text("notifications:\n  channels:\n    - type: webhook\n      enabled: ${WEBTEST_ENABLED}\n      webhook: ${WEBTEST_MISSING_WEBHOOK}\n", encoding="utf-8")
    assert load_runtime_config(source).notifications.channels[0].enabled is False


@pytest.mark.parametrize("enabled", [True, 1, "true", "yes", "on"])
def test_enabled_channel_still_requires_environment_credentials(tmp_path, monkeypatch, enabled):
    monkeypatch.delenv("WEBTEST_MISSING_WEBHOOK", raising=False)
    source = tmp_path / "config.yaml"
    source.write_text(yaml.safe_dump({"notifications": {"channels": [{"type": "webhook", "enabled": enabled,
        "webhook": "${WEBTEST_MISSING_WEBHOOK}"}]}}), encoding="utf-8")
    with pytest.raises(DslValidationError, match=r"config.notifications.channels.0.webhook.*WEBTEST_MISSING_WEBHOOK"):
        load_runtime_config(source)


def test_invalid_enabled_reports_boolean_error_before_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("WEBTEST_MISSING_WEBHOOK", raising=False)
    source = tmp_path / "config.yaml"
    source.write_text("notifications:\n  channels:\n    - type: webhook\n      enabled: invalid\n      webhook: ${WEBTEST_MISSING_WEBHOOK}\n", encoding="utf-8")
    with pytest.raises(DslValidationError, match=r"config.notifications.channels.0.enabled:.*valid boolean"):
        load_runtime_config(source)
