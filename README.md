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
├── 通知模块（邮件/钉钉）
```

## 快速开始

```bash
uv sync --dev
uv run webtest-framework examples/cases/login.xml --config examples/config/runtime.yaml --headless
```

启用 Allure 报告：

```bash
uv run webtest-framework examples/cases/login.xml --config examples/config/runtime.yaml --allure
```

## V2 Allure 增强

- 步骤级结果（case result 中包含 step 级状态与错误信息）
- 失败截图 + `runtime.log` + DSL 片段附件
- `environment.properties`（`browser` / `headless` / `python` / `version`）

## CLI 参数（核心）

- `dsl_path`：DSL 用例文件路径（支持 XML / YAML / JSON）
- `--config`：运行配置文件（YAML）
- `--browser`：`chrome` / `firefox` / `edge`
- `--headless`：无头模式
- `--log-level`：日志级别
- `--allure`：生成 Allure 结果与报告
- `--notify-email`：发送邮件通知（需配置 `smtp`）
- `--notify-dingtalk`：发送钉钉通知（需配置 `dingtalk_webhook`）

## 执行控制增强（Execution Control）

- `--include-tag-expr "<expr>"`：仅执行匹配标签表达式的 case（支持 `AND` / `OR` / `NOT` / 括号）。
- `--exclude-tag-expr "<expr>"`：排除匹配标签表达式的 case。
- `--rerunfailed <case-results.json>`：从历史结果中读取失败 case 名称，仅重跑失败用例。
- `--run-empty-suite`：当筛选后无可执行 case 时，按成功退出并产出空 `case-results.json`。
- `--merge-results <file1,file2[,fileN]>`：合并多个 case 结果文件；同名 case 以后输入覆盖前者。

示例：

```bash
# 标签表达式过滤
uv run webtest-framework examples/cases/login.xml --include-tag-expr "smoke AND NOT flaky"

# 失败重跑（可与标签过滤组合）
uv run webtest-framework examples/cases/login.xml --rerunfailed artifacts/case-results.json --exclude-tag-expr flaky

# 空套件按成功处理
uv run webtest-framework examples/cases/login.xml --include-tag-expr regression --run-empty-suite

# 结果合并（后者覆盖前者）
uv run webtest-framework --merge-results artifacts/first.json,artifacts/second.json
```

## DSL 示例

YAML：

```yaml
name: login-smoke
steps:
  - open: https://example.com/login
  - type: { selector: "#username", text: "demo" }
  - type: { selector: "#password", text: "secret" }
  - click: { selector: "button[type=submit]" }
```

JSON：

```json
{
  "name": "login-smoke",
  "steps": [
    { "open": "https://example.com/login" },
    { "type": { "selector": "#username", "text": "demo" } },
    { "type": { "selector": "#password", "text": "secret" } },
    { "click": { "selector": "button[type=submit]" } }
  ]
}
```

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
