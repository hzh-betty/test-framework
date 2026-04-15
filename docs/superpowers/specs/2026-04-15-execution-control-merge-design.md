# 执行控制与结果合并增强设计（参考 Robot Framework）

## 1. 背景与目标

对 `tmp/robotframework-master` 的扫描显示，其在 Web/自动化测试框架层面的核心优势主要是：

1. **执行入口与策略解耦**（`src/robot/run.py`）：CLI 参数与运行策略分离，便于扩展执行控制。  
2. **解析层可扩展**（`src/robot/running/builder/builders.py`）：数据解析、过滤、构建可插拔。  
3. **结果后处理独立**（`src/robot/rebot.py` + `src/robot/reporting/resultwriter.py`）：结果可二次处理、合并、重放。  
4. **可观测性与可验证性**（`atest/README.rst`）：通过标签、schema 校验、结果文件规范提升稳定性。  

本次优化目标是在你当前框架中落地：

- 标签过滤（表达式）  
- rerunfailed（基于 `case-results.json`）  
- run_empty_suite 语义  
- 多结果合并（merge）再统一出 summary/Allure

## 2. 范围与非目标

### 范围
- 在现有 `CLI -> Parser -> Executor -> Reporting` 链路上增强执行控制与结果后处理。  
- 保持现有 `--allure` 语义不变，仅增强其输入来源。  

### 非目标
- 不引入新的 DSL 文件格式（仍以 XML 为主，YAML/JSON 兼容点保留）。  
- 不改动 Selenium 关键字与 Page Object 的核心行为。  

## 3. 架构设计

新增两个子能力层：

1. **Execution Control 子层**
   - 负责标签表达式解析与 case 过滤
   - 负责 rerunfailed 输入解析与失败 case 选择
   - 负责空套件策略（默认失败，`--run-empty-suite` 允许通过）

2. **Result Merge 子层**
   - 负责合并多个 `case-results.json`
   - 同名 case 采用“后者覆盖前者”
   - 合并结果走统一 summary/Allure 产出路径

CLI 仅做参数解析与编排，不承载业务逻辑。

## 4. 数据模型变更

### 4.1 DSL Case 标签
- XML `<case>` 增加可选属性：`tags="smoke,login,critical"`  
- Parser 将其解析为 `CaseSpec.tags: list[str]`（小写归一化，去空格）

### 4.2 执行结果文件
- 新增 `case-results.json`，包含每个 case 的：
  - case 名称
  - 通过/失败状态
  - 失败消息
  - step 结果摘要（固定包含）
- 现有 `executor-summary.json` 继续保留（用于汇总展示）

## 5. CLI 接口设计

新增参数：

- `--include-tag-expr "<expr>"`  
- `--exclude-tag-expr "<expr>"`  
- `--rerunfailed <case-results.json>`  
- `--run-empty-suite`  
- `--merge-results <file1,file2,...>`

表达式语法：
- 操作符：`AND` / `OR` / `NOT`
- 支持括号：`(smoke OR critical) AND NOT flaky`
- 标签匹配大小写不敏感

## 6. 执行流程

### 6.1 普通执行
1. Parser 读取 XML 并构建 `SuiteSpec`（含 case tags）  
2. Execution Control 根据 include/exclude 表达式筛选 case  
3. 若筛选后空套件：
   - 默认返回非 0（报错）
   - 带 `--run-empty-suite` 时返回 0，并生成空 summary/报告  
4. Executor 执行后写出 `case-results.json` 与 `executor-summary.json`

### 6.2 rerunfailed
1. 读取 `--rerunfailed` 指向的 `case-results.json`  
2. 选取失败 case 名称集合  
3. 在当前 suite 中仅执行匹配 case  
4. 输出新一轮结果文件

### 6.3 merge-results
1. 读取 `--merge-results` 的多个 `case-results.json`  
2. 按 case 名合并（后者覆盖前者）  
3. 基于合并结果生成统一 `executor-summary.json` 和 Allure 结果  

## 7. 错误处理策略

1. 标签表达式非法：立即返回非 0，错误信息包含表达式位置/token  
2. `rerunfailed` / `merge-results` 文件不存在或 JSON 非法：返回非 0  
3. `merge-results` 输入为空：返回非 0  
4. 空套件默认非 0，`--run-empty-suite` 才允许 0  
5. Allure CLI 不可用时维持现有策略：记录错误，不覆盖执行结果语义

## 8. 测试策略

### 单元测试
- 标签表达式解析（AND/OR/NOT/括号/非法输入）
- include/exclude 组合过滤
- rerunfailed 读取与 case 选择
- merge 覆盖规则（后者覆盖）
- run_empty_suite 语义

### 集成测试
- XML 含 tags 的执行控制链路
- rerunfailed 的端到端重跑链路
- merge-results 后 summary/Allure 产物链路

## 9. 验收标准

满足以下即验收通过：

1. 支持 `--include-tag-expr` / `--exclude-tag-expr`，表达式语义正确  
2. 支持 `--rerunfailed case-results.json`，仅重跑失败 case  
3. 支持 `--merge-results` 并按后者覆盖规则合并  
4. 空套件语义符合约定（默认非 0，`--run-empty-suite` 为 0）  
5. 全量测试通过且回归不破坏现有 `--allure` 路径
