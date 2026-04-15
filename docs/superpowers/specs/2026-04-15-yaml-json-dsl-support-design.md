# YAML/JSON DSL Support Design

## 1. Background and Goal

Current framework supports XML DSL parsing only.  
Goal is to add **YAML and JSON DSL support** with behavior equivalent to XML, while keeping executor/reporting/notification layers unchanged.

## 2. Scope

### In Scope
- Add YAML parser and JSON parser.
- Support DSL top-level structure: `{name, cases}`.
- Keep case/step semantics equivalent to XML:
  - case: `{name, tags?, steps}`
  - step: `{action, target, value?}`
- Strict validation for unknown fields, missing required fields, and type mismatch.
- Update parser tests and README to reflect XML/YAML/JSON support.

### Out of Scope
- New DSL features not present in XML model.
- Executor/action semantics changes.
- Merge/rerun/tag-expression behavior changes.

## 3. Architecture

### 3.1 Parser Components
- `framework/parser/yaml_parser.py` → `YamlCaseParser`
- `framework/parser/json_parser.py` → `JsonCaseParser`
- Both implement existing `DslParser` protocol and output `SuiteSpec`.

### 3.2 Parser Routing
- Update `framework/parser/__init__.py::get_parser`:
  - `.xml` → `XmlCaseParser`
  - `.yaml/.yml` → `YamlCaseParser`
  - `.json` → `JsonCaseParser`

### 3.3 Shared Model
No model change required; all formats map to:
- `SuiteSpec(name, cases)`
- `CaseSpec(name, tags, steps)`
- `StepSpec(action, target, value)`

## 4. DSL Shape (YAML/JSON)

Example YAML:

```yaml
name: SmokeSuite
cases:
  - name: Login success
    tags: [smoke, login]
    steps:
      - action: open
        target: https://example.test/login
      - action: type
        target: id=username
        value: demo
```

Example JSON:

```json
{
  "name": "SmokeSuite",
  "cases": [
    {
      "name": "Login success",
      "tags": ["smoke", "login"],
      "steps": [
        {"action": "open", "target": "https://example.test/login"},
        {"action": "type", "target": "id=username", "value": "demo"}
      ]
    }
  ]
}
```

## 5. Validation and Normalization

### 5.1 Strict Validation
- Top-level allowed keys: `name`, `cases`.
- Case allowed keys: `name`, `tags`, `steps`.
- Step allowed keys: `action`, `target`, `value`.
- Unknown keys raise `ValueError` with field path.
- Missing required keys raise `ValueError` with field path.
- Type mismatch raises `ValueError` with field path.

### 5.2 Tags Normalization
- Accept `tags` as:
  - list of strings, or
  - comma-separated string.
- Normalize to: lowercase + strip + remove empty entries.
- Output type remains `list[str]`.

## 6. Error Semantics

- Parse/load failure (invalid YAML/JSON syntax): `ValueError`.
- Schema/shape/type failure: `ValueError`.
- Error message should include contextual path when possible, e.g.:
  - `cases[0].steps[1].action is required`
  - `cases[0].foo is not allowed`

## 7. Test Strategy

### 7.1 Unit Tests
- Add parser-layer tests for:
  - YAML happy path.
  - JSON happy path.
  - Unknown field rejection.
  - Required field missing.
  - Type mismatch.
  - Tags normalization parity with XML rules.

### 7.2 Regression
- Existing XML parser tests remain unchanged and must pass.
- CLI runtime tests should continue to pass with parser selection updates.

## 8. Documentation Updates

- Update README:
  - remove “V1 only XML” statements.
  - clarify `dsl_path` supports XML/YAML/JSON.
  - add minimal YAML/JSON example snippets.

## 9. Risks and Mitigations

- Risk: inconsistent validation behavior among XML/YAML/JSON.
  - Mitigation: centralize shared normalization/validation helper for YAML/JSON.
- Risk: permissive parsing hides DSL mistakes.
  - Mitigation: strict unknown-field/type checks with explicit errors.
