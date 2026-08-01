# 使用手册

> 本文档详细记录 PapersCrawler 所有**入口**、**工具**与**配置**的用法。
> 面向需要运行、调试、扩展本项目的开发者与用户。
>
> 架构设计请见 [`docs/design.md`](design.md)，变更记录请见 [`docs/tasks.md`](tasks.md)。

## 目录

- [运行模式总览](#运行模式总览)
- [CLI 模式](#cli-模式)
- [Web UI 模式](#web-ui-模式)
- [典型工作流](#典型工作流)
- [配置详解](#配置详解)
- [工具索引](#工具索引)
- [Publisher 与爬虫](#publisher-与爬虫)
- [数据流与架构](#数据流与架构)
- [测试](#测试)
- [故障排查速查](#故障排查速查)

---

## 运行模式总览

本项目支持两种互补的运行方式：

| 维度 | CLI 模式 | Web UI 模式 |
|------|---------|------------|
| **定位** | 自动化、定时任务、深度调试 | 监控仪表盘、报告工作站、交互式配置 |
| **入口** | `python tools/run_pipeline.py` **（推荐，替代旧 `src/main.py`）** | `uvicorn src.web.app:app` |
| **典型用户** | cron 调度、批量全流程 | 日常用户检查、手动生成报告 |
| **配置来源** | `src/config.py` 的 `SKIP_PHASE_*` 开关 | `src/config.py` 的 `SKIP_PHASE_*` 开关（WebUI 不覆写） |
| **典型环境** | 无头服务器（需 Xvfb 跑 Phase C） | 桌面或局域网（推荐） |
| **并发** | 单进程 | FastAPI 后台线程 + 浏览器 SSE 实时日志 |

**注意**：阶段开关（`SKIP_PHASE_*`）在 CLI 和 WebUI 间保持一致，均读取 `src/config.py` > `settings.yaml` 的配置。不再存在独立的运行时覆写层（P2 合并配置层后 `skip_overrides.json` 已移除）。

---

## CLI 模式

所有 CLI 命令通过 `PYTHONPATH=src python <脚本>` 形式调用，详见各子节。

### 全流程入口

#### `python tools/run_pipeline.py` **（推荐）**

统一流水线入口，替代 `src/main.py` / `schedule_daily.py` / `schedule_weekly.py`。

支持四种互斥模式：

| 模式 | 说明 | 等效旧入口 |
|------|------|-----------|
| `--daily` | 每日调度：Phase A-RSS/A-CR/B/C/E/E2/F | `schedule_daily.py` |
| `--weekly` | 每周调度：Phase G/H | `schedule_weekly.py` |
| `--all` | 全流程强制：忽略 SKIP 配置执行全部阶段 | `src/main.py` |
| `--phases A,B,C` | 自定义阶段列表 | — |

```bash
# 每日调度（cron 用）
python tools/run_pipeline.py --daily

# 每周调度（cron 用）
python tools/run_pipeline.py --weekly

# 全流程强制（调试用）
python tools/run_pipeline.py --all

# 选定阶段
python tools/run_pipeline.py --phases A-RSS,B,C,F
```

默认行为（不传任何模式）等效 `--all`。

**其他参数**：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--dry-run` | 关闭 | 只打印执行计划，不实际运行 |
| `--reset-publisher` / `--no-reset-publisher` | reset | 运行前重置失败 Publisher 抓取 |
| `--reset-mineru` / `--no-reset-mineru` | reset | 运行前重置失败 MinerU 解析 |
| `--log-level DEBUG\|INFO\|WARNING\|ERROR` | `LOG_LEVEL` env | 日志级别 |

自动重置逻辑与 `schedule_daily.py` 一致：
- `publisher_page_fetched_status = 'failed'` → `pending`
- `mineru_parse_status IN ('failed', 'skipped')` → `pending`

**典型 cron**：
```bash
# 每天 2:00
0 2 * * * cd /path/to/PapersCrawler && python tools/run_pipeline.py --daily

# 每周一 9:00（配合 xvfb-run）
0 9 * * 1 cd /path/to/PapersCrawler && xvfb-run -a python tools/run_pipeline.py --weekly
```

> **⚠️ `src/main.py` / `schedule_daily.py` / `schedule_weekly.py` 已弃用** —— 请迁移到 `tools/run_pipeline.py`。旧入口保留向后兼容，不再主动维护。

### 阶段开关（SKIP_PHASE）

通过 `configs/settings.yaml` 的 `skip_phases` 配置：

```yaml
skip_phases:
  A_RSS: false       # Phase A RSS 发现
  A_CR: false        # Phase A CrossRef 发现
  B: false           # CrossRef 元数据
  C: false           # Publisher 页面爬取
  E: false           # LLM 相关性
  E2: false          # MinerU PDF
  F: false           # LLM 总结
  G: false           # 报告生成
  H: true            # 邮件推送（默认关闭，需配 SMTP）
```

阶段跳过统一通过 `settings.yaml` 的 `skip_phases` 节控制。不再有独立的运行时覆写文件。

### 日志

日志文件：`data/PaperCrawler.log`（RotatingFileHandler，10MB × 5 backup）。

通过环境变量控制级别：

```bash
LOG_LEVEL=DEBUG python tools/schedule_daily.py
LOG_LEVEL=INFO  python tools/schedule_daily.py  # 生产默认
LOG_LEVEL=WARNING python tools/schedule_daily.py
```

---

## Web UI 模式

```bash
# 桌面环境
PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080

# 无头服务器（Phase C 需要虚拟显示）
xvfb-run -a bash -c 'PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080'
```

打开 http://localhost:8080。

### 页面索引

| 路由 | 页面 | 核心功能 |
|------|------|---------|
| `/` | Dashboard（302 重定向） | 自动跳转到 Dashboard |
| `/dashboard` | Dashboard | 3 统计卡片（论文总数/待报告/出版社）+ Pipeline 阶段柱状图（pending 合并到 skipped）+ 7 天采集趋势图（3 桶：reportable/total_failed/other） |
| `/papers` | Papers | 论文列表（按日期排序），默认仅显示 A/B 论文，可切 A Only / B Only / A/B / All |
| `/report` | Report | 报告查看 + 下载（只读） |

> Home / Pipeline / Logs 页面已在 2026-07-26 瘦身中删除。`/` 根路径 302 重定向到 `/dashboard`。

### Papers 页

默认查询：`llm_relevance_status='success' AND llm_relevance_category IN ('A','B')`。

参数：
- `?sort=created|published|relevance` — 排序键（默认 created）
  - `created`：按 `created_date`（入库时间）
  - `published`：按 `paperdate_rss/crossref/page`（发表日期，精度受 RSS Feed 限制）
  - `relevance`：按 `llm_relevance_date DESC`（最近被 LLM 判定的）
- `?category=a|b|ab|all` — LLM 相关性筛选（默认 `ab`）
  - `a`：仅 A 级
  - `b`：仅 B 级
  - `ab`：A 或 B（默认）
  - `all`：全部（含 C/D）

### Email 收件人配置

收件人列表通过 `data/email.yaml` 管理（详见 [data/email.yaml](#-dataemail.yaml--邮件收件人配置)），`enabled: true` 的收件人会被 Phase H 使用。文件不存在或为空时回退到 `.env SMTP_TO_ADDRS`。

### Config 页

**配置来源**：运行时配置（`configs/*.yaml`）：通过 WebUI 直接编辑，有 YAML 语法校验 + 二次确认。

**连通性测试**（一键测）：
- DeepSeek API（验证 `DEEPSEEK_API_KEY`）
- CrossRef API（验证 `CROSSREF_MAILTO`）
- MinerU API（验证 `MINERU_TOKEN`，含过期色标）

---

## 典型工作流

### 1. 从零开始的第一次运行

```bash
# 1) 安装
pip install -r requirements.txt

# 2) 复制密钥模板
cp .env.example .env
# 编辑 .env 填入 CROSSREF_MAILTO / MINERU_TOKEN / DEEPSEEK_API_KEY

# 3) 编辑研究领域定义
vim configs/keywords.yaml   # 填写 scope_definition

# 4) 全流程跑一次
python src/main.py          # 耗时取决于论文数量

# 5) 查看结果
ls data/reports/auto/        # 自动日报 Markdown
```

### 2. 日常维护（cron）

```cron
# crontab
0 10 * * * /path/to/PapersCrawler/run_daily.sh   >> /path/to/crawler_daily.log  2>&1
0 8 * * 1 /path/to/PapersCrawler/run_weekly.sh  >> /path/to/crawler_weekly.log 2>&1
```

每天早上检查邮件，每周一查汇总报告。

### 3. 修改领域定义后重新筛选

```bash
# 1) 修改 configs/keywords.yaml 的 scope_definition
# 2) 重置 LLM 相关性判断
python tools/reset_pipeline.py reset-relevance --all
# 3) 重跑后续阶段（自动从断点继续）
python src/main.py
```

### 4. Phase C 被 Cloudflare 拦截后重试

```bash
# 仅重置某个 publisher
python tools/reset_pipeline.py reset-publisher --publisher aps
# 重跑 Phase C→G
python src/main.py
```

### 5. WebUI 中快速生成特定论文的报告

1. 打开 `/report` 页
2. 用 Publisher 下拉筛选，勾选需要的论文
3. 点击 Generate → 浏览器预览 → 下载 Markdown

`report` 页生成的报告写入 `data/reports/user/`（精确到秒命名），**不**标记数据库，
不影响下次 Phase G 自动报告。

### 6. 给团队发送日报

1. `/subscriptions` 页 → 添加成员邮箱
2. 点击 "Send Report" → 勾选收件人 → 确认发送

也可通过 CLI：

```bash
python tools/schedule_weekly.py     # 完整 G→H
```

### 7. 修改报告模板/字段后预览

不写数据库、不影响下次 Phase G：

```bash
# 全部 A/B 论文
python tools/preview_report.py --scope all --output /tmp/preview.md

# 本周（ref_date 前 7 天）
python tools/preview_report.py --scope week --date 2026-07-26 --output /tmp/p.md

# 当天
python tools/preview_report.py --scope today --output /tmp/p.md

# 仅 Markdown，跳过 explainer
python tools/preview_report.py --scope all --output /tmp/p.md --no-explainer
```

详见 [`tools/preview_report.py` 文档](#报告预览)。

---

## 配置详解

### `.env` — 密钥（必须，gitignored）

```ini
# CrossRef API 联系邮箱（API 政策要求）
CROSSREF_MAILTO=your_email@example.com

# MinerU API Token（可解码 JWT 查过期时间）
MINERU_TOKEN=your_mineru_token_here

# DeepSeek API 密钥
DEEPSEEK_API_KEY=sk-your-deepseek-key

# SMTP 邮件推送（可选，不配则跳过 Phase H）
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your_email@qq.com
SMTP_PASSWORD=your_auth_code
SMTP_FROM_ADDR=your_email@qq.com
SMTP_TO_ADDRS=colleague1@example.com,colleague2@example.com
```

> 推荐迁移到 `data/email.yaml`（支持 per-user 开关，详见下文 `data/email.yaml` 节）。

`src/config.py` 通过 `os.getenv()` 读取，缺失时留空（对应功能跳过）。

### `configs/settings.yaml` — 运行参数

完整结构：

```yaml
skip_phases:                     # 阶段开关
  A_RSS: false
  A_CR: false
  B: false
  C: false
  E: false
  E2: false
  F: false
  G: false
  H: true                        # 邮件默认跳过

llm:
  relevance:                     # Phase E 相关性判断
    model: deepseek-v4-flash
    thinking: disabled
    timeout: 300
  summary:                       # Phase F 总结
    model: deepseek-v4-pro
    thinking: enabled
    timeout: 300
  concurrent_max: 100            # Phase E/F 并发上限

pipeline:
  crossref_lookback_days: 1      # A-CR 日常回溯
  crossref_lookback_days_max: 7  # A-CR 故障补漏上限
  max_papers_per_phase: 0        # 0 = 不限制
  skip_nature_news: true
  prefetch_non_research: true    # 浏览器前过滤非论文
  postfetch_non_research: true   # 抓取后再检测（兜底）
  non_research_keywords:         # 标题前缀列表（大小写不敏感）
    - "erratum"
    - "corrigendum"
    - "author correction:"
    - "publisher correction:"
    - "comment on"
    - "response to"
    - "publisher's note"

publisher:
  page_delay_min: 3              # 页面间隔（秒）
  page_delay_max: 5
  max_consecutive_failures: 3    # 连续失败 N 篇后熔断
  proxy:                         # 部分 publisher 需代理
    optica:
      server: "http://127.0.0.1:10808"

email:
  template: "detailed"           # 邮件模板名（templates/email/<name>.html）
  # 可选: default / funny / detailed

formula_fix:
  skip: false                    # FormulaFixer 是否启用
  force: false                   # 强制修复所有字段

report:
  generate_explained_html: true  # 是否生成 report_<date>_explained.html 解释页
```

### `configs/publishers.yaml` — 期刊配置

```yaml
publishers:
  - id: nature              # 唯一标识
    name: Nature            # 显示名
    publisher: nature       # 出版社 key（映射到 SCRAPER_MAP）
    rss: "https://..."      # RSS Feed URL
    issn: "0028-0836"       # CrossRef 期刊标识（可选）
    enabled: true           # 全局启用
    cr_enabled: true        # A-CR 单独开关（可选，默认 true）
    rss_enabled: true       # A-RSS 单独开关（可选，默认 true）
```

**25 个期刊**当前配置，分布：

| 出版社 | 期刊数 | 示例 |
|--------|--------|------|
| APS | 9 | PRL, PRA, PRB, PRC, PRD, PRE, PRS, RMP, ... |
| AIP | 6 | PoP, APL, JAP, ... |
| Nature | 4 | Nature, Nature Physics, Nature Photonics, Nature Communications |
| Science | 2 | Science, Science Advances |
| Optica | 2 | Optica, Optics Express |
| Cambridge | 1 | Journal of Plasma Physics |
| IOP | 1 | New Journal of Physics |

### `configs/keywords.yaml` — 研究领域定义

使用结构化字典格式（`scope_definition` + `irrelevant_fields` + `context_gates`）：

```yaml
scope_definition:
  laser_wakefield_acceleration:
    description: "本方向关注基于等离子体的尾场加速技术..."
    topics:
      - "Laser Wakefield Acceleration (LWFA) — ..."
      - "Plasma Wakefield Acceleration (PWFA) — ..."
  laser_driven_ion_acceleration:
    ...
irrelevant_fields:
  description: "以下领域即使出现相关关键词，通常也不应视为相关..."
  topics:
    - "Collider physics: high-energy hadron colliders..."
context_gates:
  - term: "fusion"
    rule: "如未明确指出 LPA/LWFA/PWFA 等离子体加速语境，归 D"
```

| 字段 | 用途 | 语种 |
|------|------|------|
| `scope_definition` | Phase E LLM prompt — 完整领域定义 | 中文 |
| `irrelevant_fields` | Phase E LLM prompt — topic 级黑名单 | 中文 |
| `context_gates` | Phase E LLM prompt — per-term 消歧规则 | 中文 |

**`scope_definition` 的子域可独立注释**，不关注的域直接 YAML 注释即可（Phase E 自动跳过）。

### `configs/prompts/*.yaml` — LLM 提示词

| 文件 | 用途 |
|------|------|
| `relevance.yaml` | Phase E 相关性判断（含 `{scope_block}` 占位符） |
| `summary.yaml` | Phase F 论文总结（中文，JSON 输出） |
| `fix.yaml` | FormulaFixer LaTeX 修复（JSON in/out） |

文件不存在时自动回退到 `src/config.py` 内嵌后备值。

### `data/email.yaml` — 邮件收件人配置

```yaml
# PapersCrawler 邮件收件人配置
#
# 字段说明:
#   - email:   收件人邮箱地址（必填）
#   - name:    显示名（可选，邮件正文中使用）
#   - enabled: 是否启用（true=发送，false=跳过；默认 true）
#
# 行为:
#   - 文件存在但解析失败/为空 → 回退 .env SMTP_TO_ADDRS
#   - 文件不存在 → 回退 .env SMTP_TO_ADDRS
#   - enabled=false 的收件人会被过滤掉
#   - Phase H 按此列表发送；空列表则跳过 Phase H

recipients:
  - email: user1@example.com
    name: "User 1"
    enabled: true
  - email: user2@example.com
    name: "User 2"
    enabled: false
```

### `data/journal_overrides.json` — 期刊启用覆写

```json
{
  "journals": {
    "nature": { "enabled": true, "rss_enabled": true, "cr_enabled": true },
    "nphys": { "enabled": false }
  }
}
```

Data Sources 页设置。CLI 模式（`force=False`）**不**读取此文件，只读 `publishers.yaml`。

---

## 工具索引

所有工具位于 `tools/` 目录，按用途分类。

#### `python tools/send_report.py`

邮件推送工具 —— 通过 Phase H 发送指定报告。

```bash
# 发送今日日报
python tools/send_report.py --report report_20260726.md

# 发送自定义报告，覆盖收件人
python tools/send_report.py --report report_20260726.md --recipients a@x.com,b@y.com

# 干跑预览
python tools/send_report.py --report report_20260726.md --dry-run
```

**参数**：

| 参数 | 必填 | 说明 |
|------|------|------|
| `--report FILENAME` | ✅ | 报告文件名（在 `auto/` 或 `user/` 目录中查找） |
| `--recipients a@x.com,b@y.com` | ❌ | 逗号分隔的收件人列表，覆盖默认配置 |
| `--dry-run` | ❌ | 只打印发送计划，不实际发送 |
| `--log-level` | ❌ | 日志级别（默认 `LOG_LEVEL` env，未设置则为 INFO） |

文件不存在时退出码为 2。

### 调度入口

| 工具 | 说明 | 典型用法 |
|------|------|---------|
| `run_pipeline.py` **（推荐）** | 统一流水线入口（替代以下三个） | `python tools/run_pipeline.py --daily` |
| `schedule_daily.py` ⚠️ **deprecated** (→ `run_pipeline.py`) | 每日 A→F，含自动重置 failed | `python tools/schedule_daily.py` |
| `schedule_weekly.py` ⚠️ **deprecated** (→ `run_pipeline.py`) | 每周 G→H | `python tools/schedule_weekly.py` |

### 邮件推送

| 工具 | 说明 | 典型用法 |
|------|------|---------|
| `send_report.py` | 通过 Phase H 发送指定报告 | `python tools/send_report.py --report report_20260726.md` |

### 状态重置

| 工具 | 说明 | 典型用法 |
|------|------|---------|
| `reset_pipeline.py` | 6 子命令重置各阶段状态 | `python tools/reset_pipeline.py reset-relevance --all` |
| `reset_empty_abstract.py` | 重置空摘要论文的 Phase E/G | `python tools/reset_empty_abstract.py` |

**`reset_pipeline.py` 子命令**：

| 子命令 | 重置列 | 级联 | 条件 |
|--------|--------|------|------|
| `reset-semantic` | `semantic_filter_*` | — | 所有非 pending |
| `reset-publisher` | `publisher_page_fetched` | — | 非 pending 且非 NonResearchPageError |
| `reset-mineru` | `mineru_parse` | — | 所有非 pending |
| `reset-summary` | `llm_summary` | report | 所有非 pending |
| `reset-relevance` | `llm_relevance` | — | 所有非 pending |
| `reset-report` | `report_status` / `report_date` | — | reported |

所有子命令支持 `--publisher` 过滤（如 `reset-publisher --publisher aps`），执行前交互确认。
**不提供一键重置全部**，防止误操作丢失数据。

### 报告生成

| 工具 | 说明 | 典型用法 |
|------|------|---------|
| `preview_report.py` | 生成报告**不**标记数据库 | `python tools/preview_report.py --output /tmp/p.md` |
| `convert_reports_to_hugo.py` | 报告转 Hugo 站点 + 部署 | `python tools/convert_reports_to_hugo.py --all --hugo --deploy` |
| `convert_md_to_pdf.py` | Markdown → PDF（pandoc + cloakbrowser 备用） | `python tools/convert_md_to_pdf.py <input.md>` |

#### 报告预览

`tools/preview_report.py` —— 生成报告但**不**调 `db.mark_papers_reported()`，完全不污染数据库；
已报告论文（`report_date NOT NULL`）也可再次包含，便于重看历史或生成回顾性快照。

**与 Phase G auto 模式的关键差异**：
1. **不调** `mark_papers_reported()` → 下次 Phase G 仍能拾取这些论文
2. SQL 去掉 `report_date IS NULL` 过滤 → 允许回看已报告论文
3. `--scope` 参数决定论文范围（`all` / `week` / `today`），按 `created_date` 过滤
4. `--output` 必填（必须 `.md` 结尾），不写默认 `data/reports/auto/`
5. explainer 文件名强制 `report_<ref_date>_explained.html`
6. `--no-explainer` 跳过解释页生成

**CLI**：
```bash
python tools/preview_report.py --scope {all,week,today} \
                              --output PATH \
                              [--date YYYY-MM-DD] \
                              [--no-explainer]
```

**适用场景**：测试报告模板/字段/排序规则变更后的渲染效果、抽查时间窗口、备份报告。

### LLM 总结修复

| 工具 | 说明 |
|------|------|
| `fix_summary_formulas.py` | 批量 FormulaFixer 修复 LaTeX（不重跑 Phase F） |

```bash
python tools/fix_summary_formulas.py                     # 修复全部
python tools/fix_summary_formulas.py --dry-run --verbose # 预览
python tools/fix_summary_formulas.py --doi <doi>         # 单篇
python tools/fix_summary_formulas.py --force              # 强制修复所有字段
```

### 手动 PDF 导入

| 工具 | 说明 |
|------|------|
| `import_local_pdf.py` | 手动导入本地 PDF 绕过 Phase E2 反复下载 |

```bash
python tools/import_local_pdf.py --doi <DOI> --pdf <PATH_TO_PDF>
```

- 校验 `%PDF-` 头部后落盘到 `data/mineru_output/<safe_doi>/paper.pdf`
- 重置 DB 该 DOI 的 `mineru_parse_status='pending'`，下次 daily 调度自动处理
- 退出码：1=文件不存在/异常，2=非 PDF 头部，3=DB 无该 DOI 记录

### 诊断

| 工具 | 用途 |
|------|------|
| `debug_llm_summary.py` | LLM Summary JSON 解析失败诊断 |
| `debug_publisher_urls.py` | headful 浏览器 Publisher 抓取诊断 |
| `debug_nature_challenge.py` | Nature Client Challenge 拦截诊断 |
| `compare_browsers.py` | 浏览器/HTTP 回退对比 |
| `test_http_fallback.py` | HTTP fallback 连通性测试 |
| `delete_accepted_papers.py` | 清理 Accepted Paper 残留（支持 `--dry-run` / `--force`） |

### 数据库迁移

| 工具 | 用途 |
|------|------|
| `migrate_db_v2.py` | 新增 `skipped_dois` 表 |
| `migrate_db_v3.py` | 删除语义相关列（Phase D 移除同步） |

### PDF 转换

```bash
# KaTeX + cloakbrowser（实验性，支持 \(\)/\[\] 公式）
python src/processors/md_to_pdf_katex.py <input.md> [output.pdf]

# pandoc + cloakbrowser（备用）
python tools/convert_md_to_pdf.py <input.md>
```

---

## Publisher 与爬虫

| 出版社 | 期刊数 | 爬虫类 | 反爬策略 |
|--------|--------|--------|---------|
| Nature | 4 | `NatureScraper` | HTTP requests 前置回退（primary） |
| Science | 2 | `ScienceScraper` | `dc.Type` + `og:type` + `altmetric_type` 三级检测 |
| APS | 9 | `APSScraper` | 同域 PDF 路径扫描 |
| Cambridge | 1 | `CambridgeScraper` | `citation_abstract` meta |
| AIP | 6 | `AIPScraper` | requests+cookie PDF 下载 |
| IOP | 1 | `IOPScraper` | curl_cffi HTTP 回退（fallback） |
| Optica | 2 | `OpticaScraper` | CrossRef 摘要驱动跳过浏览器 |

**核心策略**：
- **Persistent Context**：同 publisher 共用 Chromium session（`data/session_cached/<publisher>/`）
- **Headful Chromium + cloakbrowser**：内置浏览器指纹伪装，无需手动注入 JS
- **真人节奏**：3~5s 随机延迟（`publisher.page_delay_min/max`）
- **失败熔断**：连续 `PUBLISHER_MAX_CONSECUTIVE_FAILURES`（默认 3）篇失败后自动中止，避免 IP 封禁
- **Session 自动清理**：`close()` 后 `shutil.rmtree()` 清理 profile 目录

**PDF 下载三级兜底**（`BasePublisherScraper.download_pdf()`）：

```
[on_page_url 同域改写（仅 APS）]  →  requests + 浏览器 cookies/UA  →  context.request.get()  →  page.goto() + expect_download
                                      (主路径，最快，复用反爬 cookie)   (Optica 等内联渲染场景)      (最后兜底)
```

- **requests + cookies**：对所有 publisher 通用，绝大多数下载走此路径。
- **context.request.get()**（2026-08-01 新增）：继承浏览器代理/cookie 的子资源请求，
  解决 Optica 经代理放行后 Chrome 内联渲染 PDF 不触发 download 事件的问题。
- **on_page_url 改写**：仅 APS 启用（跨域 `link.aps.org` → 同域 `journals.aps.org` 直链）。

### Publisher 抓取错误诊断

抓取失败时，HTML 快照自动保存到 `data/raw/page/error/`，命名格式 `error_<doi>_<timestamp>.html`。
可通过 `Pipeline` 页的实时日志查看错误类型 + 页面标题 + HTML 路径。

### 非研究论文检测

Phase C 通过四级机制检测 Erratum / Corrigendum / Comment / Response / Publisher's Note：

1. **Scraper 元数据**（精确）：Nature `dc.type != "OriginalPaper"`，Science `dc.Type != "research-article"`
2. **altmetric_type**（Science 互补）：meta `altmetric_type=news|blog`
3. **og:type 兜底**：无 `dc.Type` 但有 `og:type=article`（如 Careers）
4. **关键词 + 空摘要**（通用兜底）：`settings.yaml` 的 `non_research_keywords` 前缀匹配

检测到后：写入 `skipped_dois` 表 + 从 `papers` 删除（防反复发现→删除→再发现）。

### Accepted Paper 跳过

- **APS**：`/accepted/` URL 路径检测
- **Optica**：`#articleBody` 内 `<em>accepted for publication</em>` 检测

Accepted Paper 仅从 `papers` 删除，**不**写入 `skipped_dois`（同 DOI 正式版会重新出现）。

### Nature News 过滤

`SKIP_NATURE_NEWS=True`（默认开）通过检测 DOI 中 `/d41586-` 前缀过滤 Nature 新闻类内容，
覆盖 Nature 全系列期刊的 News、News & Views、Editorials 等非研究内容。

---

## 数据流与架构

### 8 阶段流水线

```text
Phase A (RSS + CrossRef) ── 发现论文
       ↓
Phase B (CrossRef) ──────── 补充元数据（作者、日期、摘要）
       ↓
Phase C (Publisher) ─────── 爬取页面 + PDF 链接（cloakbrowser）
       ↓
Phase E (DeepSeek) ──────── LLM 判断相关性 → A/B/C/D 四级分类
       ↓                          (仅 A/B 进入下游)
Phase E2 (MinerU) ───────── PDF 全文解析
       ↓
Phase F (DeepSeek) ──────── LLM 结构化总结
       ↓
Phase G ─────────────────── Markdown 报告 + explained.html 解释页
       ↓
Phase H (SMTP) ──────────── 邮件推送（email.yaml → .env SMTP_TO_ADDRS 回退）
```

### 数据库 Schema

单表 `papers`，每阶段三态列（`status` / `error` / `date`）。每篇论文一行的全部状态：

```
┌──────────────────────────────────────────────────────────────┐
│ papers 表                                                    │
├──────────────────────────────────────────────────────────────┤
│ 核心标识: id, doi (UNIQUE)                                    │
│ 基础元数据: title, abstract, journal, publisher,              │
│            paperdate_rss/crossref/page, authors_json,        │
│            page_url, pdf_url                                 │
│ 发现来源: discovery_source (rss / crossref / rss,crossref)   │
│                                                              │
│ 流水线状态（每阶段三列）:                                    │
│   Phase B:  cr_metadata_fetched_status / _error / _date      │
│   Phase C:  publisher_page_fetched_status / _error / _date   │
│   Phase E:  llm_relevance_status / _error / _date            │
│             llm_relevance_category (A/B/C/D)                 │
│             llm_relevance_subfields (JSON 数组)              │
│   Phase E2: mineru_parse_status / _error / _date             │
│             mineru_output_dir                                │
│   Phase F:  llm_summary_status / _error / _date              │
│             llm_summary_result (JSON)                        │
│   Phase G:  report_status / report_date                      │
│                                                              │
│ 时间戳: created_date, updated_date                           │
└──────────────────────────────────────────────────────────────┘
```

状态值：`FetchStatus` 枚举（`pending` → `success` / `failed` / `skipped`）。

**辅助表**：

- `email.yaml` — 邮件收件人配置（`enabled=true` 优先于 .env `SMTP_TO_ADDRS`）
- `skipped_dois` — 被永久跳过的论文 DOI（`NonResearchPageError` 等）

### 报告输出

| 模式 | 输出目录 | 命名 | 标记已报告 | 邮件推送 |
|------|---------|------|-----------|---------|
| 自动（Phase G） | `data/reports/auto/` | `report_YYYYMMDD.md` | ✅ | ✅（Phase H） |
| 用户（WebUI `/report`） | `data/reports/user/` | `report_YYYYMMDD_HHMMSS.md` | ❌ | ❌ |
| 预览（`tools/preview_report.py`） | `--output` 指定 | 任意 `.md` | ❌ | ❌ |

`report_YYYYMMDD_explained.html` 解释页（`report.generate_explained_html: true`）默认与 md 同日同目录，
含 4 统计卡片 + 5 阶段状态柱状图 + 7 天每日采集 + 完整 relevance/summary prompt 快照。

### 邮件模板

`templates/email/<name>.html`：

- `default.html` — 正式风格
- `funny.html` — 搞笑风格
- `detailed.html` — 详细版（含追踪期刊、筛选依据、Publisher 抓取状态）

模板变量：`{report_title}` / `{paper_msg}` / `{attachment_section}` / `{journal_list}` /
`{keyword_list}` / `{domain_block}` / `{publisher_stats}` / `{paper_list}`（详细版专属）。

---

## 测试

### T1/T2 — pytest 自动化（18 个测试文件）

```bash
# 全部离线测试
pytest tests/ -v

# 单文件
pytest tests/test_runner_phase_map.py -v

# 单测
pytest tests/test_relevance.py::test_decision_tree -v
```

测试覆盖：
- `test_db.py` — 数据库 CRUD
- `test_rss.py` — RSS 解析
- `test_crossref.py` — CrossRef 元数据（mock）
- `test_publisher_parse.py` — Publisher 页面解析
- `test_relevance.py` — 相关性判断（mock + 决策树结构）
- `test_phases.py` — 阶段模块导入
- `test_report.py` — 报告生成 + 模板加载
- `test_pdf.py` — PDF 转换
- `test_email.py` — 邮件发送（mock）
- `test_runner_phase_map.py` — 锁死 `DAILY_PHASES ⊆ phase_map.keys()` 防 KeyError 回归
- `test_phase_a_lookback.py` — CrossRef 智能回溯
- `test_phase_b_authors.py` — Phase B 作者缺失标 FAILED
- `test_phase_c_bot.py` — bot 检测统一
- `test_explained_html.py` — 报告解释页模板
- `test_database_client_context.py` — DatabaseClient context manager
- `test_mineru_parser.py` — MinerU 解析
- `test_common.py` — 共享数据模型 + 异常

### T3 — 真实 API 集成测试（需 .env）

```bash
bash tests/real/run_all.sh
```

| 脚本 | 测试目标 |
|------|---------|
| `real_crossref.py` | CrossRef API 真实调用 |
| `real_llm_api.py` | DeepSeek API 真实调用 |
| `real_email.py` | SMTP 真实发送 |

T3 脚本会消耗 API 配额，谨慎运行。

---

## 故障排查速查

### 流水线完全不动

- 检查 `data/PaperCrawler.log` 最新输出
- 确认 `SKIP_PHASE_*` 没有全部置 true
- 确认 `.env` 至少填了 `DEEPSEEK_API_KEY`（Phase E 必需）

### Phase C 大量 failed（Cloudflare / Radware 拦截）

```bash
# 1) 检查网络出口 IP 信誉（机构网络通常较优）
# 2) 调高冷却时间
vim configs/settings.yaml
# publisher:
#   page_delay_min: 5
#   page_delay_max: 10
#   max_consecutive_failures: 5

# 3) 重置失败的论文
python tools/reset_pipeline.py reset-publisher --all
python src/main.py
```

HTML 快照保存在 `data/raw/page/error/`，可用浏览器打开分析拦截类型。

自 2026-08-01 起，Phase C 已内置 **Cloudflare challenge 自动恢复**：
当页面返回「请稍候…」等 Turnstile challenge 页时，`fetch_page()` 会自动 reload
（利用 challenge 页加载时写入持久化 context 的 `cf_clearance` cookie）拿到真实文章页，
无需人工干预。可通过 `configs/settings.yaml` 的 `publisher` 段调整：

```yaml
publisher:
  # challenge 页 reload 恢复次数
  challenge_max_reloads: 2
  # reload 后等待时长（毫秒）
  challenge_reload_wait_ms: 45000
```

若仍频繁失败，再考虑调大 `page_delay_min/max` 或走代理（`publisher.proxy`）。

### Phase E/F 429 限流

```bash
# 调低并发
vim configs/settings.yaml
# llm:
#   concurrent_max: 5    # 默认 100 容易触发 429
```

### Phase E2 PDF 下载失败

```bash
# 手动下载 PDF 后导入
python tools/import_local_pdf.py --doi <DOI> --pdf ~/Downloads/paper.pdf
# 下次 daily 调度会自动复用，跳过下载直接送 MinerU
```

常见失败原因：
- **Optica（Radware captcha）**：`页面未返回有效 PDF` —— 必须走代理（`configs/settings.yaml`
  `publisher.proxy.optica`），且 IP 信誉是关键（中国大陆 IP 直连会被 `opg.optica.org/captcha/` 拦截）。
  2026-08-01 起 `download_pdf()` 已改用 `context.request.get()` 抓取经代理放行的完整 PDF，
  不再依赖 `expect_download` 事件。若仍失败可尝试更换代理 IP 后重跑。
- **APS（link.aps.org 跨域）**：自动改写为同域 `journals.aps.org` 直链后下载。
- **需登录的 PDF**（少数）：`import_local_pdf.py` 手动导入。

### 邮件没收到

1. `/config` 页 → 连通性测试 → 检查 SMTP 配置
2. `/subscriptions` 页 → 确认邮箱在 `active=1` 列表
3. 查看 `data/PaperCrawler.log` 的 SMTP 连接日志（`STARTTLS`、`ehlo()` 等）
4. 检查垃圾邮件箱

### WebUI 启动失败

```bash
# 缺包
pip install fastapi uvicorn jinja2

# 端口占用
lsof -i :8080
# 换端口
PYTHONPATH=src uvicorn src.web.app:app --port 8081
```

### 数据库被锁

WebUI 和 CLI 同时跑会触发 WAL 锁等待。配置已开 `PRAGMA journal_mode=WAL`（`8c13f86` 提交），
但大量并发写仍可能短暂等待。**不要**同时跑 `python src/main.py` 和访问 WebUI 的 Pipeline 页。

### Phase D 相关报错

Phase D 已于 2026-07-24 完整移除（commit `f9a8a4f`）。如遇 "Phase D" 引用，检查是否有未清理的旧脚本或配置。

### Hugo 部署失败

```bash
# 缺 hugo / ghp-import
which hugo ghp-import
# crontab PATH 极简，必须 export
export PATH=/usr/local/bin:$PATH:/path/to/conda/bin

# 测试手动部署
python tools/convert_reports_to_hugo.py --all --hugo --deploy
```

---

## 相关文档

- [`README.md`](../README.md) — 项目首页简介
- [`docs/design.md`](design.md) — 架构设计（最高指导）
- [`docs/tasks.md`](tasks.md) — 变更流水账（关键决策、经验教训）
- `docs/doc-MinerU-Usage.md` — MinerU API 参考
- `docs/doc-Data-Sources-Invest.md` — 数据源调研
- `docs/doc-DeepSeek-ErrorCodes.md` — DeepSeek 错误码表
- `docs/reviews/` — 历次 Code Review 报告
