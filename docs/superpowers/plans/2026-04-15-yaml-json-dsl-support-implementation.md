# YAML/JSON DSL Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add strict, production-ready YAML and JSON DSL parsing with behavior equivalent to existing XML parsing.

**Architecture:** Introduce `YamlCaseParser` and `JsonCaseParser` as separate parser units, both mapping into existing `SuiteSpec/CaseSpec/StepSpec`. Add a shared strict-validation helper for YAML/JSON payload shape and tags normalization so both formats enforce identical rules. Keep executor/reporting/notification untouched by confining changes to parser layer, fixtures, and docs.

**Tech Stack:** Python 3.11, PyYAML, built-in `json`, unittest/pytest via `uv run pytest -q`

---

## File Structure

- **Create:** `framework/parser/structured_payload.py`  
  Shared YAML/JSON payload validation + model conversion helpers.
- **Create:** `framework/parser/yaml_parser.py`  
  YAML file loading and conversion to `SuiteSpec` via shared helper.
- **Create:** `framework/parser/json_parser.py`  
  JSON file loading and conversion to `SuiteSpec` via shared helper.
- **Modify:** `framework/parser/__init__.py`  
  Register YAML/JSON parser routing in `get_parser`.
- **Modify:** `tests/unit/test_parser_layer.py`  
  Add parser routing and YAML/JSON parse/validation tests.
- **Create:** `tests/fixtures/dsl/valid_case.yaml`
- **Create:** `tests/fixtures/dsl/valid_case.json`
- **Create:** `tests/fixtures/dsl/invalid_unknown_field.yaml`
- **Create:** `tests/fixtures/dsl/invalid_type.json`
- **Modify:** `README.md`  
  Update DSL support and add YAML/JSON example snippets.

### Task 1: Parser-Layer TDD for YAML/JSON

**Files:**
- Modify: `tests/unit/test_parser_layer.py`
- Create: `tests/fixtures/dsl/valid_case.yaml`
- Create: `tests/fixtures/dsl/valid_case.json`
- Create: `tests/fixtures/dsl/invalid_unknown_field.yaml`
- Create: `tests/fixtures/dsl/invalid_type.json`
- Test: `tests/unit/test_parser_layer.py`

- [ ] **Step 1: Write failing parser tests for YAML/JSON routing and happy path**

```python
from framework.parser.json_parser import JsonCaseParser
from framework.parser.yaml_parser import YamlCaseParser

    def test_get_parser_returns_yaml_parser_for_yaml_file(self):
        parser = get_parser("cases/login.yaml")
        self.assertIsInstance(parser, YamlCaseParser)

    def test_get_parser_returns_json_parser_for_json_file(self):
        parser = get_parser("cases/login.json")
        self.assertIsInstance(parser, JsonCaseParser)

    def test_yaml_parser_parses_suite_case_steps_and_tags(self):
        suite = YamlCaseParser().parse(FIXTURES / "valid_case.yaml")
        self.assertEqual(suite.name, "SmokeSuite")
        self.assertEqual(suite.cases[0].name, "Login success")
        self.assertEqual(suite.cases[0].tags, ["smoke", "login"])
        self.assertEqual(suite.cases[0].steps[0].action, "open")

    def test_json_parser_parses_suite_case_steps_and_tags(self):
        suite = JsonCaseParser().parse(FIXTURES / "valid_case.json")
        self.assertEqual(suite.name, "SmokeSuite")
        self.assertEqual(suite.cases[0].name, "Login success")
        self.assertEqual(suite.cases[0].tags, ["smoke", "login"])
        self.assertEqual(suite.cases[0].steps[0].target, "https://example.test/login")
```

- [ ] **Step 2: Write failing tests for strict validation**

```python
    def test_yaml_parser_raises_on_unknown_field(self):
        with self.assertRaises(ValueError):
            YamlCaseParser().parse(FIXTURES / "invalid_unknown_field.yaml")

    def test_json_parser_raises_on_type_mismatch(self):
        with self.assertRaises(ValueError):
            JsonCaseParser().parse(FIXTURES / "invalid_type.json")
```

- [ ] **Step 3: Add fixture files used by tests**

```yaml
# tests/fixtures/dsl/valid_case.yaml
name: SmokeSuite
cases:
  - name: Login success
    tags: "smoke, login"
    steps:
      - action: open
        target: https://example.test/login
      - action: type
        target: id=username
        value: demo
```

```json
{
  "name": "SmokeSuite",
  "cases": [
    {
      "name": "Login success",
      "tags": ["smoke", "login"],
      "steps": [
        {"action": "open", "target": "https://example.test/login"},
        {"action": "click", "target": "id=submit"}
      ]
    }
  ]
}
```

```yaml
# tests/fixtures/dsl/invalid_unknown_field.yaml
name: SmokeSuite
cases:
  - name: Login success
    foo: bar
    steps:
      - action: open
        target: https://example.test/login
```

```json
{
  "name": "SmokeSuite",
  "cases": [
    {
      "name": "Login success",
      "steps": [
        {"action": "open", "target": 123}
      ]
    }
  ]
}
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_parser_layer.py`  
Expected: FAIL with import errors for `YamlCaseParser` / `JsonCaseParser` and/or parser routing failures.

- [ ] **Step 5: Commit test scaffolding**

```bash
git add tests/unit/test_parser_layer.py tests/fixtures/dsl/valid_case.yaml tests/fixtures/dsl/valid_case.json tests/fixtures/dsl/invalid_unknown_field.yaml tests/fixtures/dsl/invalid_type.json
git commit -m "test(parser): add yaml json parser behavior specs" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Shared Structured Payload Validator

**Files:**
- Create: `framework/parser/structured_payload.py`
- Test: `tests/unit/test_parser_layer.py`

- [ ] **Step 1: Implement minimal shared validation/conversion helper**

```python
# framework/parser/structured_payload.py
from __future__ import annotations

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec


def build_suite_from_mapping(payload: dict, source: str) -> SuiteSpec:
    _require_mapping(payload, source)
    _reject_unknown_keys(payload, {"name", "cases"}, source)
    name = _require_str(payload, "name", source)
    cases_value = _require_list(payload, "cases", source)
    cases = [_build_case(case, f"{source}.cases[{index}]") for index, case in enumerate(cases_value)]
    return SuiteSpec(name=name, cases=cases)
```

- [ ] **Step 2: Implement strict case/step validation and tags normalization**

```python
def _build_case(raw_case: object, path: str) -> CaseSpec:
    _require_mapping(raw_case, path)
    _reject_unknown_keys(raw_case, {"name", "tags", "steps"}, path)
    name = _require_str(raw_case, "name", path)
    steps_raw = _require_list(raw_case, "steps", path)
    tags = _normalize_tags(raw_case.get("tags", []), f"{path}.tags")
    steps = [_build_step(step, f"{path}.steps[{index}]") for index, step in enumerate(steps_raw)]
    return CaseSpec(name=name, tags=tags, steps=steps)


def _build_step(raw_step: object, path: str) -> StepSpec:
    _require_mapping(raw_step, path)
    _reject_unknown_keys(raw_step, {"action", "target", "value"}, path)
    action = _require_str(raw_step, "action", path)
    target = _require_str(raw_step, "target", path)
    value = raw_step.get("value")
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{path}.value must be a string when provided.")
    return StepSpec(action=action, target=target, value=value)
```

- [ ] **Step 3: Run parser-layer tests**

Run: `uv run pytest -q tests/unit/test_parser_layer.py`  
Expected: still FAIL, now mainly due missing YAML/JSON parser classes/routing.

- [ ] **Step 4: Commit shared helper**

```bash
git add framework/parser/structured_payload.py
git commit -m "feat(parser): add strict structured payload validator" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Add YAML Parser and Route by Extension

**Files:**
- Create: `framework/parser/yaml_parser.py`
- Modify: `framework/parser/__init__.py`
- Modify: `tests/unit/test_parser_layer.py`
- Test: `tests/unit/test_parser_layer.py`

- [ ] **Step 1: Implement YAML parser**

```python
# framework/parser/yaml_parser.py
from __future__ import annotations

from pathlib import Path

import yaml

from .structured_payload import build_suite_from_mapping


class YamlCaseParser:
    def parse(self, case_file: str | Path):
        path = Path(case_file)
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML DSL file: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("YAML DSL root must be a mapping object.")
        return build_suite_from_mapping(payload, source="dsl")
```

- [ ] **Step 2: Wire parser routing for YAML**

```python
# framework/parser/__init__.py
from .yaml_parser import YamlCaseParser

def get_parser(case_file: str | Path) -> DslParser:
    dsl_format = detect_format(case_file)
    if dsl_format is DslFormat.XML:
        return XmlCaseParser()
    if dsl_format is DslFormat.YAML:
        return YamlCaseParser()
    raise NotImplementedError(
        f"Parser for '{dsl_format.value}' is not implemented. "
        "Use XML/YAML/JSON input."
    )
```

- [ ] **Step 3: Run parser tests**

Run: `uv run pytest -q tests/unit/test_parser_layer.py`  
Expected: FAIL only on JSON parser tests.

- [ ] **Step 4: Commit YAML parser**

```bash
git add framework/parser/yaml_parser.py framework/parser/__init__.py tests/unit/test_parser_layer.py
git commit -m "feat(parser): add yaml dsl parser" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Add JSON Parser and Finalize Parser Exports

**Files:**
- Create: `framework/parser/json_parser.py`
- Modify: `framework/parser/__init__.py`
- Modify: `tests/unit/test_parser_layer.py`
- Test: `tests/unit/test_parser_layer.py`

- [ ] **Step 1: Implement JSON parser**

```python
# framework/parser/json_parser.py
from __future__ import annotations

import json
from pathlib import Path

from .structured_payload import build_suite_from_mapping


class JsonCaseParser:
    def parse(self, case_file: str | Path):
        path = Path(case_file)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON DSL file: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON DSL root must be an object.")
        return build_suite_from_mapping(payload, source="dsl")
```

- [ ] **Step 2: Wire parser routing and exports for JSON**

```python
# framework/parser/__init__.py
from .json_parser import JsonCaseParser

def get_parser(case_file: str | Path) -> DslParser:
    dsl_format = detect_format(case_file)
    if dsl_format is DslFormat.XML:
        return XmlCaseParser()
    if dsl_format is DslFormat.YAML:
        return YamlCaseParser()
    if dsl_format is DslFormat.JSON:
        return JsonCaseParser()
    raise NotImplementedError(
        f"Parser for '{dsl_format.value}' is not implemented. "
        "Use XML/YAML/JSON input."
    )

__all__ = [
    "DslParser",
    "XmlCaseParser",
    "YamlCaseParser",
    "JsonCaseParser",
    "get_parser",
]
```

- [ ] **Step 3: Update/replace old YAML not-implemented assertion**

```python
# tests/unit/test_parser_layer.py
    def test_get_parser_raises_for_unimplemented_yaml(self):
        with self.assertRaises(NotImplementedError):
            get_parser("cases/login.yaml")
```

Replace with:

```python
    def test_get_parser_returns_yaml_parser_for_yaml_file(self):
        parser = get_parser("cases/login.yaml")
        self.assertIsInstance(parser, YamlCaseParser)
```

- [ ] **Step 4: Run parser-focused tests**

Run: `uv run pytest -q tests/unit/test_parser_layer.py tests/unit/test_dsl_contract.py`  
Expected: PASS

- [ ] **Step 5: Commit JSON parser**

```bash
git add framework/parser/json_parser.py framework/parser/__init__.py tests/unit/test_parser_layer.py
git commit -m "feat(parser): add json dsl parser" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: CLI/Docs Alignment and Regression

**Files:**
- Modify: `README.md`
- Test: `tests/unit/test_parser_layer.py`
- Test: `tests/unit/test_cli_runtime.py`
- Test: `tests/integration/test_execution_control_flow.py`

- [ ] **Step 1: Update README DSL support statements**

```markdown
## 架构分层
├── DSL层（XML / YAML / JSON）

## CLI 参数（核心）
- `dsl_path`：DSL 用例文件路径（支持 XML / YAML / JSON）
```

- [ ] **Step 2: Add concise YAML/JSON DSL examples in README**

````markdown
### YAML DSL 示例
```yaml
name: SmokeSuite
cases:
  - name: Login success
    steps:
      - action: open
        target: https://example.test/login
```

### JSON DSL 示例
```json
{
  "name": "SmokeSuite",
  "cases": [
    {"name": "Login success", "steps": [{"action": "open", "target": "https://example.test/login"}]}
  ]
}
```
````

- [ ] **Step 3: Run targeted regression**

Run: `uv run pytest -q tests/unit/test_parser_layer.py tests/unit/test_cli_runtime.py tests/integration/test_execution_control_flow.py`  
Expected: PASS

- [ ] **Step 4: Run full regression**

Run: `uv run pytest -q`  
Expected: PASS

- [ ] **Step 5: Commit docs/regression closure**

```bash
git add README.md
git commit -m "docs: document yaml json dsl support" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
