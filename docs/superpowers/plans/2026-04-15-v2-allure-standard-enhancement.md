# V2 Allure Standard Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 `--allure` 开关语义不变的前提下，实现步骤级 Allure 结果、失败截图+运行日志+DSL 片段附件、以及环境信息写入。  

**Architecture:** 继续沿用 `CLI -> Executor -> AllureReporter` 路径，不改执行引擎核心调度。通过新增 `ReportContext` 把运行环境与输入文件信息传给 reporter；reporter 负责统一落盘 result/附件/environment。Allure 生成失败仅记录日志，不改变测试执行退出码逻辑。  

**Tech Stack:** Python 3.12, uv, pytest, Selenium, Allure CLI, JSON 文件写入

---

## File Structure

- Modify: `framework/reporting/allure_reporter.py`（ReportContext、result/附件/environment 生成）
- Modify: `framework/cli/main.py`（构建并传递 ReportContext，处理 Allure 失败日志）
- Modify: `tests/unit/test_allure_report_module.py`（reporter 单测增强）
- Modify: `tests/unit/test_cli_runtime.py`（CLI 传参与失败行为校验）
- Create: `tests/integration/test_allure_artifacts_flow.py`（端到端 Allure 产物验证）
- Modify: `README.md`（V2 Allure 增强行为说明）

### Task 1: Reporter Contract（ReportContext + environment）

**Files:**
- Modify: `tests/unit/test_allure_report_module.py`
- Modify: `framework/reporting/allure_reporter.py`
- Test: `tests/unit/test_allure_report_module.py`

- [ ] **Step 1: 写失败测试（ReportContext + environment）**

```python
def test_write_environment_properties_contains_required_fields(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = AllureReporter(results_dir=Path(tmpdir) / "allure-results")
        context = ReportContext(
            browser="chrome",
            headless=True,
            python_version="3.12.3",
            framework_version="0.1.0",
            runtime_log_path="artifacts/runtime.log",
            dsl_path="examples/cases/login.xml",
        )
        env_path = reporter.write_environment_properties(context)
        content = env_path.read_text(encoding="utf-8")
        assert "browser=chrome" in content
        assert "headless=true" in content
        assert "python=3.12.3" in content
        assert "version=0.1.0" in content
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/unit/test_allure_report_module.py::TestAllureReportModule::test_write_environment_properties_contains_required_fields`  
Expected: FAIL（`ReportContext` 或 `write_environment_properties` 未定义）

- [ ] **Step 3: 最小实现 ReportContext 和 environment 写入**

```python
@dataclass(frozen=True)
class ReportContext:
    browser: str
    headless: bool
    python_version: str
    framework_version: str
    runtime_log_path: str | None
    dsl_path: str | None

def write_environment_properties(self, context: ReportContext) -> Path:
    self.results_dir.mkdir(parents=True, exist_ok=True)
    env = self.results_dir / "environment.properties"
    env.write_text(
        "\n".join(
            [
                f"browser={context.browser}",
                f"headless={str(context.headless).lower()}",
                f"python={context.python_version}",
                f"version={context.framework_version}",
            ]
        ),
        encoding="utf-8",
    )
    return env
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest -q tests/unit/test_allure_report_module.py::TestAllureReportModule::test_write_environment_properties_contains_required_fields`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_allure_report_module.py framework/reporting/allure_reporter.py
git commit -m "feat(reporting): add report context and environment properties"
```

### Task 2: 步骤级结果 + 三类附件

**Files:**
- Modify: `tests/unit/test_allure_report_module.py`
- Modify: `framework/reporting/allure_reporter.py`
- Test: `tests/unit/test_allure_report_module.py`

- [ ] **Step 1: 写失败测试（steps + screenshot/log/dsl 附件）**

```python
def test_write_suite_result_contains_steps_and_attachments(self):
    result = SuiteExecutionResult(
        name="Smoke",
        total_cases=1,
        passed_cases=0,
        failed_cases=1,
        case_results=[
            CaseExecutionResult(
                name="Login",
                passed=False,
                step_results=[
                    StepExecutionResult(
                        action="assert_text",
                        target="id=welcome",
                        passed=False,
                        error_message="mismatch",
                    )
                ],
                error_message="mismatch",
            )
        ],
    )
    context = ReportContext(
        browser="chrome",
        headless=True,
        python_version="3.12.3",
        framework_version="0.1.0",
        runtime_log_path="artifacts/runtime.log",
        dsl_path="examples/cases/login.xml",
    )
    reporter.write_suite_result(result, context=context)
    files = list(reporter.results_dir.glob("*-result.json"))
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["steps"][0]["name"] == "assert_text id=welcome"
    assert "attachments" in payload
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/unit/test_allure_report_module.py::TestAllureReportModule::test_write_suite_result_contains_steps_and_attachments`  
Expected: FAIL（`write_suite_result` 无 `context` 参数或缺少 `steps/attachments`）

- [ ] **Step 3: 最小实现步骤与附件元信息**

```python
def _build_step_payload(self, step: StepExecutionResult) -> dict:
    return {
        "name": f"{step.action} {step.target}",
        "status": "passed" if step.passed else "failed",
        "statusDetails": {"message": step.error_message or ""},
    }

def _build_attachments(self, context: ReportContext) -> list[dict]:
    attachments: list[dict] = []
    if context.runtime_log_path:
        attachments.append({"name": "runtime.log", "type": "text/plain", "source": "runtime.log"})
    if context.dsl_path:
        attachments.append({"name": "dsl-snippet.xml", "type": "text/plain", "source": "dsl-snippet.xml"})
    return attachments
```

- [ ] **Step 4: 运行模块测试确认通过**

Run: `uv run pytest -q tests/unit/test_allure_report_module.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_allure_report_module.py framework/reporting/allure_reporter.py
git commit -m "feat(reporting): add step-level allure result and attachments"
```

### Task 3: CLI 报告上下文接线与失败容错

**Files:**
- Modify: `tests/unit/test_cli_runtime.py`
- Modify: `framework/cli/main.py`
- Modify: `framework/reporting/allure_reporter.py`
- Test: `tests/unit/test_cli_runtime.py`

- [ ] **Step 1: 写失败测试（CLI 传 context + 生成失败仅日志）**

```python
def test_main_passes_report_context_to_reporter(self):
    captured = {}
    class ReporterSpy(FakeReporter):
        def write_suite_result(self, result, context=None):
            captured["browser"] = context.browser
            return super().write_suite_result(result)
    deps = RuntimeDependencies(
        driver_manager_factory=lambda: FakeDriverManager(),
        actions_factory=lambda _driver: object(),
        executor_factory=lambda _actions, _logger: FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                case_results=[],
            )
        ),
        reporter_factory=lambda _dir: ReporterSpy(),
        logger_factory=lambda _level, _file: FakeLogger(),
        email_notifier_factory=lambda _config: FakeNotifier(),
        dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
    )
    rc = main([str(xml_file), "--allure", "--browser", "chrome"], dependencies=deps)
    assert rc == 0
    assert captured["browser"] == "chrome"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/unit/test_cli_runtime.py::TestCliRuntime::test_main_passes_report_context_to_reporter`  
Expected: FAIL（`write_suite_result` 未收到 context）

- [ ] **Step 3: 实现 CLI -> reporter context 传递**

```python
context = ReportContext(
    browser=browser,
    headless=headless,
    python_version=platform.python_version(),
    framework_version=__version__,
    runtime_log_path=args.log_file,
    dsl_path=args.dsl_path,
)
reporter.write_suite_result(suite_result, context=context)
reporter.write_environment_properties(context)
generated = reporter.generate_html_report(output_dir=args.allure_report_dir)
if not generated and hasattr(logger, "error"):
    logger.error("Allure report generation failed")
```

- [ ] **Step 4: 运行 CLI 单测确认通过**

Run: `uv run pytest -q tests/unit/test_cli_runtime.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_cli_runtime.py framework/cli/main.py framework/reporting/allure_reporter.py
git commit -m "feat(cli): pass allure report context and keep non-blocking failure policy"
```

### Task 4: 端到端产物验证 + 文档更新

**Files:**
- Create: `tests/integration/test_allure_artifacts_flow.py`
- Modify: `README.md`
- Test: `tests/integration/test_allure_artifacts_flow.py`

- [ ] **Step 1: 写失败集成测试（产物完整性）**

```python
def test_allure_artifacts_flow(tmp_path):
    results_dir = tmp_path / "allure-results"
    report_dir = tmp_path / "allure-report"
    xml_file = tmp_path / "case.xml"
    xml_file.write_text(
        "<suite name='Smoke'><case name='Login'><step action='open' target='https://example.test' /></case></suite>",
        encoding="utf-8",
    )
    deps = RuntimeDependencies(
        driver_manager_factory=lambda: FakeDriverManager(),
        actions_factory=lambda _driver: object(),
        executor_factory=lambda _actions, _logger: FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                case_results=[
                    CaseExecutionResult(
                        name="Login",
                        passed=True,
                        step_results=[StepExecutionResult(action="open", target="https://example.test", passed=True)],
                    )
                ],
            )
        ),
        reporter_factory=lambda _dir: AllureReporter(results_dir=results_dir),
        logger_factory=lambda _level, _file: FakeLogger(),
        email_notifier_factory=lambda _config: FakeNotifier(),
        dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
    )
    rc = main([str(xml_file), "--allure", "--allure-results-dir", str(results_dir), "--allure-report-dir", str(report_dir)], dependencies=deps)
    assert rc == 0
    assert any(results_dir.glob("*-result.json"))
    assert (results_dir / "environment.properties").exists()
    assert (results_dir / "executor-summary.json").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest -q tests/integration/test_allure_artifacts_flow.py`  
Expected: FAIL（产物不完整或测试尚未接线）

- [ ] **Step 3: 最小实现缺失产物写入并更新 README**

```markdown
## V2 Allure 增强
- 步骤级结果
- 失败截图 + runtime.log + DSL 片段附件
- environment.properties（browser/headless/python/version）
```

- [ ] **Step 4: 运行全量测试**

Run: `uv run pytest -q`  
Expected: PASS（全部测试通过）

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_allure_artifacts_flow.py README.md
git commit -m "test/docs: validate v2 allure artifacts end-to-end"
```

### Task 5: 最终回归与交付检查

**Files:**
- Test: 全量测试命令

- [ ] **Step 1: 运行最终回归**

Run: `uv run pytest -q`  
Expected: PASS

- [ ] **Step 2: 核对 CLI 行为**

Run: `uv run webtest-framework examples/cases/login.xml --config examples/config/runtime.yaml --allure --headless`  
Expected: 生成 `artifacts/allure-results` 和 `artifacts/allure-report`；Allure CLI 缺失时仅记录错误日志

- [ ] **Step 3: Commit**

```bash
git add .
git commit -m "feat(v2): complete standard allure enhancement"
```
