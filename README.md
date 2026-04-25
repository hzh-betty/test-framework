# test-framework

`test-framework` 现在是一个基于 YAML 的 Web 自动化测试框架，核心包为`webtest_core`，命令行入口为 `webtest`。

## 架构

- `webtest_core.dsl`：加载 YAML 测试套件和运行配置，并使用 Pydantic 做结构校验。
- `webtest_core.keywords`：注册关键字库，并把 DSL 参数绑定到 Python 函数。
- `webtest_core.browser`：封装 Selenium 细节，向关键字层提供稳定的浏览器动作。
- `webtest_core.runtime`：执行套件、重试、筛选、dry-run 和并行用例。
- `webtest_core.reports`：写出用例结果、统计数据、HTML 报告和 Allure 结果文件。
- `webtest_core.integrations`：处理通知等外部集成。
- `webtest_core.cli`：把以上模块组装成 `webtest` 命令。

## 快速开始

```bash
uv sync --dev
uv run webtest run examples/smoke.yaml --config examples/runtime.yaml --dry-run --html-report
```

命令会生成：

- `artifacts/case-results.json`
- `artifacts/statistics.json`
- `artifacts/html-report/index.html`

## 命令行

```bash
webtest run <suite.yaml> [options]
```

常用参数：

- `--config examples/runtime.yaml`：指定运行配置。
- `--browser chrome|firefox|edge`：指定浏览器。
- `--headless`：启用无头模式。
- `--dry-run`：只校验和模拟执行，不启动真实浏览器。
- `--workers 4`：设置并行用例数量。
- `--run-empty-suite`：筛选后没有可执行用例时按成功处理，并产出空结果。
- `--include-tag-expr "smoke AND login"`：只执行匹配标签表达式的用例。
- `--exclude-tag-expr "slow"`：排除匹配标签表达式的用例。
- `--module auth`：按模块筛选。
- `--case-type ui`：按用例类型筛选。
- `--priority p0`：按优先级筛选。
- `--owner qa-web`：按负责人筛选。
- `--rerun-failed artifacts/case-results.json`：只重跑历史失败用例。
- `--merge-results file1.json,file2.json`：合并多个结果文件。
- `--output-dir artifacts`：指定输出目录。
- `--html-report`：生成内置中文 HTML 测试报告。
- `--allure`：生成 Allure 结果文件。
- `--notify`：按运行配置发送通知。
- `--deploy`：执行运行配置中的部署命令。

## YAML 测试套件

框架只支持 YAML DSL，不支持 XML，也不支持旧的 `action` / `target` / `value`
字段。测试套件以 `suite` 为根节点，包含 `name`、可选的 `variables`、`setup`、
`teardown`、可复用 `keywords` 和 `cases`。每个用例可以声明模块、类型、优先级、
负责人、标签、重试和步骤。

```yaml
suite:
  name: 冒烟测试
  variables:
    base_url: https://example.test
  cases:
    - name: 登录页可以访问
      module: auth
      type: ui
      priority: p0
      owner: qa-web
      tags: [smoke]
      steps:
        - keyword: Open
          args: ["${base_url}/login"]
        - keyword: Assert URL Contains
          args: [login]
```

步骤使用新语法：

```yaml
- keyword: Wait Visible
  args: [id=username]
  timeout: 500ms
  retry: 1
  continue_on_failure: false
```

支持的超时单位包括 `500ms`、`2s`、`1 minute`。动作名支持 Robot 风格规范化，
例如 `Wait Visible`、`wait-visible`、`wait_visible` 等价。

## 示例

`examples/smoke.yaml` 是能力展示型示例，覆盖变量、suite/case 生命周期、复合关键字、
标签与元数据、重试、失败继续、超时、Web 关键字、HTTP 关键字和报告输出。示例中的
域名与定位器是占位值，建议先用 dry-run 验证框架执行流：

```bash
uv run webtest run examples/smoke.yaml --config examples/runtime.yaml --dry-run --html-report --allure
```

HTTP 片段示例：

```yaml
- keyword: HTTP GET
  args: ["https://api.example.test/users/1"]
  kwargs:
    headers:
      Authorization: Bearer token
    timeout: 3
- keyword: Assert Response Status
  args: [200]
- keyword: Assert Response JSON
  args: ["data.user.name", "Alice"]
- keyword: Assert Response Header
  args: ["content-type", "application/json"]
```

## 关键字速查

定位器支持严格前缀：`id`、`name`、`css`、`xpath`、`class`、`tag`、`link`、
`partial_link`、`text`、`partial_text`、`testid`、`data-testid`。没有前缀时默认
按 CSS 选择器处理。JSON 字段路径使用点号读取对象和数组，例如 `data.items.0.name`。

| 分类 | 关键字 | 功能简述 |
| --- | --- | --- |
| 浏览器会话 | `New Browser` | 按别名懒加载一个浏览器会话。 |
| 浏览器会话 | `Switch Browser` | 切换到指定别名的浏览器会话。 |
| 浏览器会话 | `Close Browser` | 关闭当前浏览器会话。 |
| 基础 Web | `Open` | 打开指定 URL。 |
| 基础 Web | `Click` | 点击定位到的元素。 |
| 基础 Web | `Type Text` | 清空输入框后输入文本。 |
| 基础 Web | `Clear` | 清空定位到的输入元素。 |
| 基础 Web | `Assert Text` | 断言元素文本包含期望内容。 |
| 基础 Web | `Screenshot` | 保存当前浏览器截图。 |
| 等待/断言 | `Wait Visible` | 等待元素可见，支持 `timeout`。 |
| 等待/断言 | `Wait Not Visible` | 等待元素不可见，支持 `timeout`。 |
| 等待/断言 | `Wait Gone` | 等待元素消失或不可见，支持 `timeout`。 |
| 等待/断言 | `Wait Clickable` | 等待元素可点击，支持 `timeout`。 |
| 等待/断言 | `Wait Text` | 等待元素包含指定文本，支持 `timeout`。 |
| 等待/断言 | `Wait URL Contains` | 等待当前 URL 包含指定片段，支持 `timeout`。 |
| 等待/断言 | `Assert Element Visible` | 断言元素当前可见。 |
| 等待/断言 | `Assert Element Contains` | 断言元素文本包含期望内容。 |
| 等待/断言 | `Assert URL Contains` | 断言当前 URL 包含指定片段。 |
| 等待/断言 | `Assert Title Contains` | 断言页面标题包含指定文本。 |
| 交互扩展 | `Select` | 按可见文本选择下拉框选项。 |
| 交互扩展 | `Hover` | 鼠标悬停到定位元素。 |
| 交互扩展 | `Switch Frame` | 切换 frame，支持 `default`、`parent`、数字索引和元素定位符。 |
| 交互扩展 | `Switch Window` | 切换窗口，支持窗口句柄或数字索引。 |
| 交互扩展 | `Accept Alert` | 接受当前浏览器弹窗。 |
| 交互扩展 | `Upload File` | 向文件输入框写入本地文件路径。 |
| HTTP 请求 | `HTTP Request` | 使用指定 HTTP 方法请求 URL，并保存最近一次响应。 |
| HTTP 请求 | `HTTP GET` | 发起 GET 请求。 |
| HTTP 请求 | `HTTP POST` | 发起 POST 请求，支持 `data` 或 `json` 请求体。 |
| HTTP 请求 | `HTTP PUT` | 发起 PUT 请求。 |
| HTTP 请求 | `HTTP PATCH` | 发起 PATCH 请求。 |
| HTTP 请求 | `HTTP DELETE` | 发起 DELETE 请求。 |
| HTTP 断言 | `Assert Response Status` | 断言最近一次响应状态码。 |
| HTTP 断言 | `Assert Response Header` | 断言最近一次响应 Header 的精确值。 |
| HTTP 断言 | `Assert Response JSON` | 按点号路径断言最近一次响应 JSON 字段。 |
| HTTP 断言 | `Assert Response Body Contains` | 断言最近一次响应正文包含指定文本。 |

## 报告与可观测性

`case-results.json` 包含 suite teardown 状态、用例结果和步骤级诊断字段：
`failure_type`、`call_chain`、`duration_ms`、`retry_attempt`、`retry_max_retries`、
`case_attempt`、`case_max_retries`、`retry_trace`、`resolved_locator`、`current_url`。

开启 `--allure` 后会生成 `executor-summary.json`、`environment.properties` 和
Allure case result JSON；开启 `--html-report` 后会生成中文 HTML 测试报告。

## 通知

传入 `--notify` 后，框架会读取 `notifications.channels` 并按 `trigger`
发送结果摘要。当前支持邮件、钉钉、飞书和通用 webhook：

| 类型 | 配置字段 | 发送格式 |
| --- | --- | --- |
| `email` | `smtp` | SMTP 邮件，正文为测试结果摘要。 |
| `dingtalk` | `webhook` | 钉钉机器人 markdown 消息。 |
| `feishu` | `webhook` | 飞书机器人 post 消息。 |
| `webhook` | `webhook` | 原始 JSON 结果摘要。 |

## 运行配置

运行配置同样使用 YAML。可以通过 `${ENV_NAME}` 引用环境变量，框架会在校验
前完成替换。

```yaml
browser: chrome
headless: true
timeouts:
  implicit_wait: 5
pipeline:
  deploy:
    commands:
      - python -c "print('部署占位命令')"
notifications:
  channels:
    - type: email
      enabled: false
      trigger: on_failure
      retries: 1
      smtp:
        host: smtp.example.com
        port: 465
        username: ${WEBTEST_SMTP_USERNAME}
        password: ${WEBTEST_SMTP_PASSWORD}
        sender: webtest@example.com
        receivers:
          - qa@example.com
          - dev@example.com
    - type: dingtalk
      enabled: false
      trigger: on_failure
      retries: 1
      webhook: ${WEBTEST_DINGTALK_WEBHOOK}
    - type: feishu
      enabled: false
      trigger: always
      retries: 1
      webhook: ${WEBTEST_FEISHU_WEBHOOK}
```
