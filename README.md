# test-framework

基于 **Python + uv + Selenium** 的分层 Web 自动化测试框架，支持 DSL 用例导入、执行、日志、Allure 报告与通知扩展。

## 架构分层

```text
├── DSL层（XML / YAML / JSON，V1先实现XML）
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

- `dsl_path`：DSL 用例文件路径（V1 为 XML）
- `--config`：运行配置文件（YAML）
- `--browser`：`chrome` / `firefox` / `edge`
- `--headless`：无头模式
- `--log-level`：日志级别
- `--allure`：生成 Allure 结果与报告
- `--notify-email`：发送邮件通知（需配置 `smtp`）
- `--notify-dingtalk`：发送钉钉通知（需配置 `dingtalk_webhook`）

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
