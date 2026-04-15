# V2 Allure 增强设计（标准增强方案）

## 1. 目标与范围

本次 V2 仅增强 Allure 报告能力，保持现有执行链路和 `--allure` 开关行为不变。  
目标是让报告具备可定位问题所需的最小完备信息：

1. 步骤级执行结果（step 级状态/错误信息）
2. 失败步骤截图附件
3. 运行日志附件
4. 原始 DSL 片段附件
5. 环境信息文件 `environment.properties`（`browser/headless/python/version`）

## 2. 约束与非目标

### 约束
- 仅在传入 `--allure` 时产出 Allure 结果与 HTML 报告。
- Allure CLI 不可用时，不影响测试执行结果退出码（仅记录错误）。
- 附件写入失败不得覆盖原始测试失败原因。

### 非目标
- 本次不实现趋势历史、TestOps 对接、复杂分类统计。
- 不改 DSL 语法，不改 Executor 核心调度规则。

## 3. 架构方案

在现有 `framework/reporting/allure_reporter.py` 基础上增强：

1. `write_suite_result()`  
   - 继续写 `executor-summary.json`
   - 为每个 case 生成标准 `*-result.json`
   - 将 step 展开到 `steps` 节点
2. 附件写入能力  
   - 失败步骤截图（若路径存在）
   - 全局运行日志附件（`runtime.log`）
   - DSL 原始片段附件（当前执行文件内容）
3. `write_environment_properties()`  
   - 输出 `environment.properties`
4. `generate_html_report()`  
   - 维持 `allure generate`，异常转换为 `False`

CLI (`framework/cli/main.py`) 继续统一调用 `_handle_reporting()`。

## 4. 数据流

1. CLI 解析参数并执行 `Executor`
2. `Executor` 返回 `SuiteExecutionResult`
3. `_handle_reporting()` 在 `--allure` 打开时调用 `AllureReporter`：
   - `write_suite_result(result, context)`：写 summary + case result + step details
   - `write_environment_properties(context)`：写环境信息
   - `attach_runtime_log(path)` 和 `attach_dsl_snippet(path)`：写附件元信息
   - `generate_html_report()`
4. 失败/异常策略：
   - CLI 仅记录 Allure 生成异常，不改变执行结果返回码逻辑

## 5. 关键数据结构（扩展）

新增/扩展一个 `ReportContext`（可在 reporter 内部 dataclass）：

- `browser: str`
- `headless: bool`
- `python_version: str`
- `framework_version: str`
- `runtime_log_path: str | None`
- `dsl_path: str | None`

`write_suite_result()` 接收 `SuiteExecutionResult + ReportContext`，保证产物可追溯。

## 6. 错误处理

1. **Allure CLI 不存在/执行失败**  
   - `generate_html_report()` 返回 `False`
   - CLI 记录错误日志
2. **附件不存在/读取失败**  
   - 记录 warning 或 error
   - 不抛出覆盖执行错误
3. **JSON 写入失败**  
   - 抛出 `RuntimeError` 给调用方，由 CLI 统一处理并打印

## 7. 测试策略

新增/更新测试：

1. `tests/unit/test_allure_report_module.py`
   - case+step 结果结构校验
   - 失败截图附件元信息
   - runtime.log 与 DSL 片段附件元信息
   - environment.properties 字段校验
2. `tests/unit/test_cli_runtime.py`
   - `--allure` 开启路径行为
   - Allure 生成失败时只记录错误
3. 回归：
   - `uv run pytest -q` 全量通过

## 8. 验收标准

满足以下条件即视为完成：

1. `--allure` 开启后，`allure-results` 包含：
   - case 级 `*-result.json`
   - `environment.properties`
   - summary 文件
   - 附件元信息（截图/日志/DSL）
2. 失败步骤在结果中可见错误信息，并可定位到截图附件
3. Allure CLI 缺失时不影响用例执行退出码
4. 全量测试通过
