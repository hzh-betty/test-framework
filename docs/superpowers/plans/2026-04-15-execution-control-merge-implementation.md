# Execution Control & Result Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前框架增加标签表达式过滤、rerunfailed、run_empty_suite 与多结果合并能力，并保持现有 Allure 链路可用。

**Architecture:** 在 `CLI -> Parser -> Executor -> Reporting` 主链路上新增两个可复用能力：`execution_control`（筛选、空套件语义、rerunfailed case 选择）和 `result_merge`（合并多个 case-results 再统一产出 summary/Allure）。CLI 仅编排，业务逻辑下沉到独立模块。

**Tech Stack:** Python 3.12, uv, pytest, dataclasses, JSON, existing Selenium/Allure modules

---

### Task 1: DSL Case Tags 支持

**Files:**
- Modify: `framework/dsl/models.py`
- Modify: `framework/dsl/schema/test_case.xsd`
- Modify: `framework/parser/xml_parser.py`
- Modify: `tests/unit/test_parser_layer.py`
- Test: `tests/unit/test_parser_layer.py`

- [ ] **Step 1: 写失败测试（解析 tags）**

```python
def test_xml_parser_parses_case_tags(self):
    suite = XmlCaseParser().parse(FIXTURES / "valid_case_with_tags.xml")
    self.assertEqual(suite.cases[0].tags, ["smoke", "login"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/unit/test_parser_layer.py::TestParserLayer::test_xml_parser_parses_case_tags`  
Expected: FAIL with `AttributeError: 'CaseSpec' object has no attribute 'tags'` or assertion mismatch.

- [ ] **Step 3: 最小实现 tags 模型与解析**

```python
# framework/dsl/models.py
@dataclass(frozen=True)
class CaseSpec:
    name: str
    tags: list[str] = field(default_factory=list)
    steps: list[StepSpec] = field(default_factory=list)

# framework/parser/xml_parser.py
raw_tags = case.attrib.get("tags", "")
tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]
cases.append(CaseSpec(name=case.attrib["name"], tags=tags, steps=steps))
```

- [ ] **Step 4: 更新 XSD 并回归测试**

```xml
<!-- framework/dsl/schema/test_case.xsd -->
<xs:attribute name="tags" type="xs:string" use="optional" />
```

Run: `uv run pytest -q tests/unit/test_parser_layer.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add framework/dsl/models.py framework/dsl/schema/test_case.xsd framework/parser/xml_parser.py tests/unit/test_parser_layer.py
git commit -m "feat(dsl): support case tags in xml parser"
```

### Task 2: 标签表达式解析与过滤器

**Files:**
- Create: `framework/executor/tag_expression.py`
- Create: `tests/unit/test_tag_expression.py`
- Test: `tests/unit/test_tag_expression.py`

- [ ] **Step 1: 写失败测试（AND/OR/NOT/括号）**

```python
def test_tag_expression_eval_complex():
    expr = compile_tag_expression("(smoke OR critical) AND NOT flaky")
    assert expr({"smoke", "api"}) is True
    assert expr({"critical", "flaky"}) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/unit/test_tag_expression.py::test_tag_expression_eval_complex`  
Expected: FAIL with `ImportError` or `NameError` for `compile_tag_expression`.

- [ ] **Step 3: 最小实现表达式编译器**

```python
# framework/executor/tag_expression.py
def compile_tag_expression(expression: str):
    tokens = tokenize(expression)
    parser = Parser(tokens)
    node = parser.parse_expr()
    if parser.has_remaining():
        raise ValueError("Unexpected token at end of expression")
    return lambda tags: node.eval({t.lower() for t in tags})
```

- [ ] **Step 4: 覆盖非法表达式测试**

```python
def test_tag_expression_invalid_syntax():
    with pytest.raises(ValueError):
        compile_tag_expression("smoke AND OR critical")
```

Run: `uv run pytest -q tests/unit/test_tag_expression.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add framework/executor/tag_expression.py tests/unit/test_tag_expression.py
git commit -m "feat(executor): add tag expression compiler"
```

### Task 3: 执行控制（include/exclude + run_empty_suite）

**Files:**
- Create: `framework/executor/execution_control.py`
- Modify: `framework/executor/runner.py`
- Modify: `framework/cli/main.py`
- Modify: `tests/unit/test_executor_engine.py`
- Modify: `tests/unit/test_cli_runtime.py`
- Test: `tests/unit/test_executor_engine.py`

- [ ] **Step 1: 写失败测试（过滤后空套件语义）**

```python
def test_run_suite_fails_when_filtered_empty_and_not_allowed():
    suite = SuiteSpec(name="S", cases=[CaseSpec(name="C1", tags=["smoke"], steps=[])])
    executor = Executor(page_factory=lambda: FakePage([]))
    with pytest.raises(ValueError):
        executor.run_suite(
            suite,
            include_tag_expr="regression",
            run_empty_suite=False,
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/unit/test_executor_engine.py::test_run_suite_fails_when_filtered_empty_and_not_allowed`  
Expected: FAIL because `run_suite` does not accept new args.

- [ ] **Step 3: 实现 execution_control 与 runner 接线**

```python
# framework/executor/execution_control.py
def select_cases(cases, include_expr=None, exclude_expr=None, allowed_case_names=None):
    include_fn = compile_tag_expression(include_expr) if include_expr else None
    exclude_fn = compile_tag_expression(exclude_expr) if exclude_expr else None
    selected = []
    for case in cases:
        tags = set(case.tags)
        if allowed_case_names and case.name not in allowed_case_names:
            continue
        if include_fn and not include_fn(tags):
            continue
        if exclude_fn and exclude_fn(tags):
            continue
        selected.append(case)
    return selected

# framework/executor/runner.py
selected_cases = select_cases(
    suite.cases,
    include_expr=include_tag_expr,
    exclude_expr=exclude_tag_expr,
    allowed_case_names=allowed_case_names,
)
if not selected_cases and not run_empty_suite:
    raise ValueError("Suite contains no runnable cases after filtering.")
```

- [ ] **Step 4: 添加 CLI 参数并验证**

```python
# framework/cli/main.py parser
parser.add_argument("--include-tag-expr", default=None)
parser.add_argument("--exclude-tag-expr", default=None)
parser.add_argument("--run-empty-suite", action="store_true")
```

Run: `uv run pytest -q tests/unit/test_executor_engine.py tests/unit/test_cli_runtime.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add framework/executor/execution_control.py framework/executor/runner.py framework/cli/main.py tests/unit/test_executor_engine.py tests/unit/test_cli_runtime.py
git commit -m "feat(execution): add include/exclude filters and empty-suite strategy"
```

### Task 4: case-results 输出与 rerunfailed

**Files:**
- Create: `framework/reporting/case_results.py`
- Modify: `framework/cli/main.py`
- Modify: `tests/unit/test_cli_runtime.py`
- Create: `tests/unit/test_case_results.py`
- Test: `tests/unit/test_case_results.py`

- [ ] **Step 1: 写失败测试（写入/读取 case-results）**

```python
def test_case_results_roundtrip(tmp_path):
    data = [{"name": "Login", "passed": False, "error_message": "mismatch"}]
    path = tmp_path / "case-results.json"
    write_case_results(path, data)
    loaded = read_case_results(path)
    assert loaded[0]["name"] == "Login"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/unit/test_case_results.py::test_case_results_roundtrip`  
Expected: FAIL with `ImportError`.

- [ ] **Step 3: 实现结果读写与 rerunfailed 选择**

```python
# framework/reporting/case_results.py
def write_case_results(path: Path, cases: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def read_failed_case_names(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {c["name"] for c in data.get("cases", []) if not c.get("passed", True)}
```

```python
# framework/cli/main.py
parser.add_argument("--rerunfailed", default=None)
allowed_case_names = read_failed_case_names(Path(args.rerunfailed)) if args.rerunfailed else None
suite_result = executor.run_file(
    args.dsl_path,
    include_tag_expr=args.include_tag_expr,
    exclude_tag_expr=args.exclude_tag_expr,
    allowed_case_names=allowed_case_names,
    run_empty_suite=args.run_empty_suite,
)
write_case_results(Path("artifacts/case-results.json"), to_case_result_dicts(suite_result))
```

- [ ] **Step 4: 回归 CLI 行为测试**

Run: `uv run pytest -q tests/unit/test_case_results.py tests/unit/test_cli_runtime.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add framework/reporting/case_results.py framework/cli/main.py tests/unit/test_case_results.py tests/unit/test_cli_runtime.py
git commit -m "feat(reporting): add case-results file and rerunfailed support"
```

### Task 5: merge-results 合并与统一报告链路

**Files:**
- Create: `framework/reporting/result_merge.py`
- Modify: `framework/cli/main.py`
- Create: `tests/unit/test_result_merge.py`
- Modify: `tests/unit/test_cli_runtime.py`
- Test: `tests/unit/test_result_merge.py`

- [ ] **Step 1: 写失败测试（后者覆盖规则）**

```python
def test_merge_case_results_later_file_overrides_earlier():
    merged = merge_case_results(
        [{"name": "Login", "passed": False}],
        [{"name": "Login", "passed": True}],
    )
    assert merged["Login"]["passed"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/unit/test_result_merge.py::test_merge_case_results_later_file_overrides_earlier`  
Expected: FAIL with `ImportError`.

- [ ] **Step 3: 实现 merge 模块与 CLI 合并分支**

```python
# framework/reporting/result_merge.py
def merge_case_results(*groups: list[dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        for case in group:
            merged[case["name"]] = case
    return merged

# framework/cli/main.py
parser.add_argument("--merge-results", default=None)
if args.merge_results:
    merged_suite_result = build_suite_result_from_case_files(args.merge_results)
    _handle_reporting(args, merged_suite_result, dependencies, logger, report_context)
    return 0 if merged_suite_result.failed_cases == 0 else 1
```

- [ ] **Step 4: 验证 merge 路径不依赖 WebDriver**

```python
def test_main_merge_results_skips_driver_creation():
    deps = RuntimeDependencies(
        driver_manager_factory=lambda: (_ for _ in ()).throw(RuntimeError("driver should not be created")),
        actions_factory=lambda _driver: object(),
        executor_factory=lambda _actions, _logger: FakeExecutor(make_suite_result()),
        reporter_factory=lambda _dir: FakeReporter(),
        logger_factory=lambda _level, _file: FakeLogger(),
        email_notifier_factory=lambda _config: FakeNotifier(),
        dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
    )
    rc = main(["dummy.xml", "--merge-results", "a.json,b.json"], dependencies=deps)
    assert rc in (0, 1)
```

Run: `uv run pytest -q tests/unit/test_result_merge.py tests/unit/test_cli_runtime.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add framework/reporting/result_merge.py framework/cli/main.py tests/unit/test_result_merge.py tests/unit/test_cli_runtime.py
git commit -m "feat(reporting): add merge-results with overwrite semantics"
```

### Task 6: 集成测试与文档收口

**Files:**
- Create: `tests/integration/test_execution_control_flow.py`
- Modify: `README.md`
- Test: `tests/integration/test_execution_control_flow.py`

- [ ] **Step 1: 写失败集成测试（过滤 + rerun + merge）**

```python
def test_execution_control_and_merge_flow(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text('{"cases":[{"name":"Login","passed":false}]}', encoding="utf-8")
    second.write_text('{"cases":[{"name":"Login","passed":true},{"name":"Search","passed":true}]}', encoding="utf-8")
    merged = merge_case_results(
        json.loads(first.read_text(encoding="utf-8"))["cases"],
        json.loads(second.read_text(encoding="utf-8"))["cases"],
    )
    summary = {"total_cases": len(merged), "failed_cases": sum(1 for c in merged.values() if not c["passed"])}
    assert summary["total_cases"] >= 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/integration/test_execution_control_flow.py`  
Expected: FAIL with missing options or behavior mismatch.

- [ ] **Step 3: 更新 README 执行控制章节**

```markdown
## 执行控制增强
- --include-tag-expr / --exclude-tag-expr
- --rerunfailed <case-results.json>
- --run-empty-suite
- --merge-results <file1,file2[,fileN]>
```

- [ ] **Step 4: 运行全量回归**

Run: `uv run pytest -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_execution_control_flow.py README.md
git commit -m "test/docs: cover execution control and merge workflow"
```
