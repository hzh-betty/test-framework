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
uv sync --dev --locked
uv run webtest run examples/smoke.yaml --config examples/runtime.yaml --dry-run --html-report
```

每次运行都会创建独立目录，`artifacts/latest-run.json` 的 `directory` 指向本次产物。
该目录包含：

- `case-results.json`
- `statistics.json`
- `runtime.log`
- `html-report/index.html`

## 命令行

```bash
webtest run <suite.yaml> [options]
```

常用参数：

- `--config examples/runtime.yaml`：指定运行配置。
- `--browser chrome|firefox|edge`：指定浏览器。
- `--headless` / `--no-headless`：覆盖配置中的无头模式。
- `--dry-run`：校验名称、参数、变量、定位器、超时和复合调用图；不启动浏览器、不请求 HTTP、不部署或发送通知。
- `--workers 4`：设置并行用例数量。
- `--run-empty-suite`：允许筛选后零用例；suite 初始化和清理失败仍返回失败。
- `--include-tag-expr "smoke AND login"`：只执行匹配标签表达式的用例。
- `--exclude-tag-expr "slow"`：排除匹配标签表达式的用例。
- `--module auth`：按模块筛选。
- `--case-type ui`：按用例类型筛选。
- `--priority p0`：按优先级筛选。
- `--owner qa-web`：按负责人筛选。
- `--rerun-failed <run-directory>/case-results.json`：按当前套件身份重跑失败或未执行的用例；历史生命周期失败时重跑该套件所有用例。
- `--merge-results file1.json,file2.json`：以稳定套件和用例标识合并，同一身份后文件覆盖；显示名称脱敏不影响身份。
- `--output-dir artifacts`：指定产物根目录；运行结果写入 `runs/<run-id>/`。
- `--html-report` / `--no-html-report`：覆盖配置中的 HTML 报告开关。
- `--allure` / `--no-allure`：覆盖配置中的 Allure 输出开关。
- `--notify`：按运行配置发送通知。
- `--deploy`：执行运行配置中的部署命令。

## YAML 测试套件

框架只支持 YAML DSL，不支持 XML，也不支持旧的 `action` / `target` / `value`
字段。测试套件以 `suite` 为根节点，包含 `name`、可选的 `variables`、`setup`、
`teardown`、可复用 `keywords` 和 `cases`。每个用例可以声明模块、类型、优先级、
负责人、标签、重试和步骤。

套件和配置中的重复 YAML 键会报告行列并拒绝加载；合并键 `<<` 引入的默认值允许
显式覆盖。

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

支持的超时单位包括 `500ms`、`2s`、`1 minute`、`2 minutes`。timeout 是关键字
支持的 I/O 等待参数；不能给 Open、Click 等没有 timeout 参数的关键字声明总时间预算。
动作名和复合关键字名支持 Robot 风格规范化，
例如 `Wait Visible`、`wait-visible`、`wait_visible` 等价。

套件内用例名必须唯一。复合关键字只声明步骤列表，不接受 args、kwargs 或 timeout；
其 retry 会重新执行整个子流程，循环引用在执行前拒绝。`${name}` 独占一个值时保留
数字、布尔、列表和对象类型，混合文本引用转换为字符串；变量缺失或循环引用会报错。

## 生命周期与进程内 API

suite setup/teardown 共用一个套件上下文，每个用例尝试使用独立的浏览器会话和
HTTP 响应。suite setup 登录不会传递浏览器给用例；登录复合关键字应放在 case setup。
teardown 会尝试全部步骤，自动资源清理会尝试关闭全部会话，失败均写入报告。

自定义执行使用工厂，每次调用创建新的有状态库对象。工厂只组装资源，不启动浏览器：

```python
from webtest_core.browser import BrowserConfig, BrowserSessionActions
from webtest_core.keywords import KeywordRegistry
from webtest_core.keywords.http import HttpKeywordLibrary
from webtest_core.keywords.web import WebKeywordLibrary
from webtest_core.runtime import SuiteExecutor

def registry_factory():
    actions = BrowserSessionActions(BrowserConfig(headless=True))
    return KeywordRegistry.from_libraries(
        [WebKeywordLibrary(actions), HttpKeywordLibrary()],
        diagnostics=actions.diagnostics,
        cleanup=actions.close_all,
    )

executor = SuiteExecutor(registry_factory)
```

不要在工厂中返回共享的浏览器或 HttpKeywordLibrary。用于控制外部服务行为的测试
替身可以显式共享计数器；用例执行状态必须独立。

kwargs 中的授权、Cookie、password、token 等键会脱敏。Type Text 的密码定位器会
自动脱敏文本；其他敏感位置参数使用 `sensitive_args: [0]` 声明。原值仍传给动作，
结果、日志、错误与 DSL 附件使用脱敏副本。
变量别名和 case 覆盖按插值后的实际值收集；数字敏感参数也会屏蔽，统计计数和时间保持原值。
直接调用报告或通知 API 时，可传 `redactor=executor.redactor` 复用执行时收集的秘密。

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
`text` / `partial_text` 选择最内层匹配节点，支持嵌套标签文字；CSS 属性选择器中的等号
无需添加前缀。JSON 断言区分布尔值和数字，`1` 与 `1.0` 同属数字；HTTP timeout 必须大于零。

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

`case-results.json` 包含整体 `passed`、独立的 setup/teardown 步骤、用例结果和诊断字段：
`failure_type`、`call_chain`、`duration_ms`、`retry_attempt`、`retry_max_retries`、
`case_attempt`、`case_max_retries`、`retry_trace`、`resolved_locator`、`current_url`。
用例的 `attempts` 保存每次尝试；步骤 `retry_trace` 保存自身重试，复合步骤的
`children` 保存子步骤。suite setup 或部署失败的用例标为 `blocked`，不计入执行失败数。
CLI 依据整体 passed 返回 0/1，生命周期失败不会因零用例而被忽略。
中断返回 130，`latest-run.json` 标记 `interrupted`，保留已完成用例并尽力写出报告。
结果中的 `suite_id` / `case_id` 从原始套件名和用例名生成稳定 SHA256，供合并和失败重跑使用；
`start` / `stop` 记录实际毫秒时间。读取历史结果会拒绝成功状态与最终步骤、尝试或子步骤的矛盾。
直接调用 `read_failed_case_names` 可传 `case_names` 提供当前用例名，恢复已脱敏显示名称。

CLI 将相对截图路径保存到本次运行的 `cases/<id>/attempt-<n>/` 或 `suite/` 下，拒绝向上逃逸；
绝对路径按用户声明使用。HTML 和 Allure 复制 PNG 附件并关联到步骤。

开启 `--allure` 后会生成 `executor-summary.json`、`environment.properties` 和
Allure case result JSON，附件复制到本次结果目录；开启 `--html-report` 后会生成中文 HTML 报告。
直接调用 Allure 写入函数时要求空目录，避免混入旧结果。Allure 结果由框架直接生成，
不需要 allure-python-commons，查看报告时另行使用 Allure CLI。

## 通知

传入 `--notify` 后，框架会读取 `notifications.channels` 并按 `trigger`
发送结果摘要。当前支持邮件、钉钉、飞书和通用 webhook：

触发条件使用套件整体状态，包含初始化、清理和部署失败。通知失败会打印并写入
`notification_errors`，不改变测试本身的退出码。SMTP 默认超时 10 秒，部署默认超时
300 秒。启用渠道必须有对应配置，缺失环境变量会报路径；禁用渠道允许缺失凭证。
SMTP 部分拒收会记录错误并停止该条消息重试，避免给已收件的地址重复发送。

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
  implicit_wait: 0
  explicit_wait: 10
logging:
  level: INFO
  file: runtime.log
reports:
  html: true
  allure: false
pipeline:
  deploy:
    timeout: 300
    commands:
      - [python, "-c", "print('部署占位命令')"]
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

CLI 开关优先于 reports/headless 配置。logging.file 的相对路径基于本次运行目录，
绝对路径按配置使用。部署 commands 使用参数数组，直接启动程序；需要 shell 时显式
声明 `cmd /c` 或 `bash -c` 及其参数。默认隐式等待为 0；配置非零值时，显式等待期间会暂时关闭它并
在结束后恢复，避免影响短等待时间。
部署超时或中断会回收所监督的进程树：Windows 使用 Job Object，POSIX 使用进程组。

## 开发验证

```bash
uv run pytest -q
uv build
```

GitHub Actions 在 Ubuntu 和 Windows、Python 3.11 和 3.13 上执行锁定依赖测试、构建及
wheel 安装后的示例 dry-run。测试使用本地服务与替身，不发送真实通知或启动浏览器；
实际 XPath 节点语义测试需要 PowerShell/.NET，缺少该环境时会跳过。
