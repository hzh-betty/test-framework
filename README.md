# test-framework

基于 **Python + uv + Selenium** 的分层 Web 自动化测试框架，支持 DSL 用例导入、执行、日志、Allure 报告与通知扩展。

## 架构分层

```text
├── DSL层（XML / YAML / JSON）
├── 解析层（Parser）
├── 执行引擎（Executor）
├── Selenium封装层
├── Page Object层
├── 报告模块（Allure）
├── 日志模块
└── 通知模块（邮件/钉钉）
```

## 快速开始

```bash
uv sync --dev

# 关键字 DSL 示例
uv run webtest-framework examples/cases/web_actions_extended.yaml --config examples/config/runtime.yaml --dry-run

# XML 关键字/生命周期/变量示例
uv run webtest-framework examples/cases/keyword_lifecycle.xml --config examples/config/runtime.yaml --headless

# 扩展 Web 关键字示例（支持并行参数）
uv run webtest-framework examples/cases/web_actions_extended.yaml --config examples/config/runtime.yaml --workers 2 --headless
```

> 提示：示例中的 URL / 定位符（如 `https://example.test`、`id=...`）为演示占位符，请替换为你的目标系统实际地址与元素定位。

启用 Allure：

```bash
uv run webtest-framework examples/cases/web_actions_extended.yaml --config examples/config/runtime.yaml --allure --dry-run
```

## DSL 能力（当前实现）

- 支持 suite / case 级 `setup`、`teardown`、`variables`。
- 支持 case / step 级 `retry`（非负整数）与 `continue_on_failure`（布尔）。
- 支持变量插值：`\${var}`，可用于 `keyword` / `args` / `kwargs` / `timeout`。
- step 统一使用 `keyword`、`args`、`kwargs`、`timeout`：
  - YAML/JSON：`{keyword: Type Text, args: [id=username, demo]}`
  - XML：`<step keyword="Type Text"><arg value="id=username" /><arg value="demo" /></step>`
- 支持用户复合关键字（`keywords`），调用时直接把用户关键字名写到 `keyword`。
- 支持步骤级 `timeout` 字段/属性，等待动作可写 `timeout="500ms"`、`timeout="2s"`、`timeout="1 minute"`；未提供时默认 10 秒。
- 支持标签与筛选：`tags`、`--include-tag-expr`、`--exclude-tag-expr`。
- `--dry-run` 只执行解析、变量替换、关键字查找、参数绑定、类型转换、定位器和 timeout 校验，不启动 WebDriver。

## 内置 Web 关键字

- 基础：`Open`、`Click`、`Type Text`、`Clear`、`Assert Text`、`Screenshot`
- 等待/断言：`Wait Visible`、`Wait Not Visible`、`Wait Gone`、`Wait Clickable`、`Wait Text`、`Wait URL Contains`、`Assert Element Visible`、`Assert Element Contains`、`Assert URL Contains`、`Assert Title Contains`
- 交互扩展：`Select`、`Hover`、`Switch Frame`、`Switch Window`、`Accept Alert`、`Upload File`
- 浏览器会话：`New Browser`、`Switch Browser`、`Close Browser`

说明：
- `Wait Visible` / `Wait Clickable` / `Wait Text` / `Wait URL Contains` / `Assert Element Visible` / `Accept Alert` 使用 `timeout` 控制等待时间。
- 定位器支持严格前缀：`id`、`name`、`css`、`xpath`、`class`、`tag`、`link`、`partial_link`、`text`、`partial_text`、`testid` / `data-testid`；无前缀默认 CSS。
- 关键字名支持 Robot 风格规范化，例如 `Wait Visible`、`wait-visible`、`wait_visible` 等价。
- `Switch Frame` 支持 `default` / `parent` / 数字索引 / 元素定位符。
- `Switch Window` 支持窗口句柄或数字索引。

## 执行控制与并行

- `--workers <N>`：case 级并行 worker 数。
  - `0` 或 `1`：串行执行
  - `>1`：并行执行
- 并行模式仅并发 case；suite 级 `setup` 与 `teardown` 各执行一次。
- case 结果顺序与筛选后输入顺序一致。
- `workers > 1` 时，CLI 为每个线程懒加载独立 WebDriver，并在结束后统一回收。

## 报告与可观测性

- `artifacts/case-results.json` 除 case 列表外，包含：
  - `suite_teardown_failed`
  - `suite_teardown_error_message`
  - `suite_teardown_failure_type`
- 步骤级结果包含关键诊断元数据：
  - `keyword_name`、`arguments`、`keyword_source`、`dry_run`
  - `failure_type`、`call_chain`
  - `duration_ms`
  - `retry_attempt` / `retry_max_retries`
  - `case_attempt` / `case_max_retries`
  - `retry_trace`
  - `resolved_locator`
  - `current_url`
- Allure 增强：
  - `executor-summary.json` 汇总
  - 步骤级状态、失败类型与诊断字段
  - 附件：失败截图、`runtime.log`、DSL 片段
  - `environment.properties`：`browser` / `headless` / `python` / `version`

## 执行控制增强（Execution Control）

- `--include-tag-expr "<expr>"`：仅执行匹配标签表达式的 case（支持 `AND` / `OR` / `NOT` / 括号）。
- `--exclude-tag-expr "<expr>"`：排除匹配标签表达式的 case。
- `--rerunfailed <case-results.json>`：从历史结果中读取失败 case 名称，仅重跑失败用例。
- `--run-empty-suite`：当筛选后无可执行 case 时，按成功退出并产出空 `case-results.json`。
- `--merge-results <file1,file2[,fileN]>`：合并多个 case 结果文件；同名 case 以后输入覆盖前者。

## 示例用例

- `examples/cases/web_actions_extended.yaml`：关键字 DSL、扩展 Web 动作与超时语法示例。
- `examples/cases/login.xml`：XML 关键字登录示例。
- `examples/cases/keyword_lifecycle.xml`：关键词 + 生命周期 + 变量 + 重试/容错。
- `examples/cases/web_actions_extended.xml`：扩展 Web 动作与超时语法示例。

## 目录结构

```text
framework/
  core/
  dsl/
  parser/
  selenium/
  page_objects/
  executor/
  logging/
  reporting/
  notify/
  cli/
tests/
  unit/
  integration/
examples/
  cases/
  config/
```
