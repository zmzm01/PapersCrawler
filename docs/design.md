> 此文档描述**需求**与**架构设计**。

# 项目需求

自动抓取领域核心期刊文章，筛选与组内工作相关的论文，生成结构化报告并推送。

# 项目结构

```
PapersCrawler/
├── AGENTS.md                    # AI 辅助上下文（供 opencode 使用）
├── .env.example                 # 密钥模板（复制为 .env 后填写）
├── configs/
│   ├── publishers.yaml          # 需要追踪的期刊配置 (RSS Feed + 出版社)
│   ├── keywords.yaml            # 研究领域定义（scope_definition + irrelevant + embedding）
│   ├── settings.yaml            # 运行参数（阶段开关、LLM 模型、爬虫等）
│   └── prompts/                 # LLM Prompt 模板目录
│       ├── summary.yaml         #   Phase F 论文总结 prompt
│       ├── relevance.yaml       #   Phase E 相关性判断 prompt（含 scope_block 占位符）
│       └── fix.yaml             #   FormulaFixer 公式修复 prompt
├── data/
│   ├── papers.db                # SQLite 数据库 (自动生成)
│   ├── PaperCrawler.log         # 运行日志
│   ├── raw/
│   │   ├── rss/                 # RSS Feed XML 缓存
│   │   └── page/                # Publisher 页面 HTML 缓存 (调试用)
│   ├── reports/                 # 生成的 Markdown 报告
│   │   ├── auto/                #   自动日报 (Phase G 自动, 按日期覆盖)
│   │   └── user/                #   用户自选报告 (Web UI, 精确到秒)
│   ├── mineru_output/           # MinerU PDF 解析输出 (按论文子目录)
│   └── session_cached/          # 浏览器 Session 缓存 (按 publisher 分子目录)
├── docs/                        # 设计文档、数据源调研、API 参考
│   ├── design.md                # 本文 — 需求与架构设计
│   ├── tasks.md                 # 执行步骤、关键决策、经验教训
│   ├── usage.md                 # 详细使用手册（所有入口/工具/配置）
│   ├── doc-MinerU-Usage.md      # MinerU API 使用参考
│   ├── doc-Data-Sources-Invest.md  # 数据源调研记录
│   ├── doc-DeepSeek-ErrorCodes.md  # DeepSeek 错误码表
│   └── reviews/                 # 历次 Code Review 报告
├── slides/                      # 报告/演示文稿区域 (预留)
├── templates/                   # 非 Web UI 模板
│   └── email/                   #   邮件 HTML 模板 (default.html)
├── tests/                       # 测试 (T1/T2: pytest 自动化, T3: 手动真实测试)
│   ├── conftest.py              # pytest 配置 (src 路径)
│   ├── fixtures/                # 真实响应快照 (由 T3 脚本生成)
│   ├── real/                    # T3 真实测试脚本 (需 .env 配置)
│   │   ├── real_crossref.py     #   CrossRef API 真实调用
│   │   ├── real_llm_api.py      #   DeepSeek API 真实调用
│   │   ├── real_email.py        #   SMTP 真实发送
│   │   └── run_all.sh           #   一键运行全部 T3 测试
│   ├── test_db.py               # 数据库操作
│   ├── test_rss.py              # RSS 解析
│   ├── test_crossref.py         # CrossRef 元数据 (mock)
│   ├── test_publisher_parse.py  # Publisher 页面解析
│   ├── test_relevance.py        # 相关性判断 (mock)
│   ├── test_phases.py           # 阶段模块导入测试
│   ├── test_report.py           # 报告生成
│   ├── test_pdf.py              # PDF 转换
│   └── test_email.py            # 邮件发送 (mock)
├── src/
│   ├── common.py                # 共享数据模型 (Paper dataclass) + 共享异常
│   ├── config.py                # 全局配置 (路径、密钥来自 .env)
│   ├── main.py                  # CLI 入口 (委托 pipeline.runner)
│   ├── db/
│   │   └── database.py          # SQLite 数据库 CRUD + FetchStatus 枚举
│   ├── sources/                 # 数据源
│   │   ├── rss.py               # RSS Feed 抓取与解析 (返回 Paper dataclass)
│   │   ├── crossref.py          # CrossRef DOI 元数据查询 (返回 PaperMetadata)
│   │   └── publisher.py         # 7 个出版社的 cloakbrowser 页面抓取器
│   ├── processors/              # 业务逻辑处理器 (原 utils/)
│   │   ├── paper_relevance.py   # 语义过滤器 + LLM 相关性判断
│   │   ├── llm_summarize_deepseek.py  # DeepSeek API 论文总结
│   │   ├── mineru_paper_parser.py     # MinerU API PDF 全文解析
│   │   ├── paper_report_generator.py  # Markdown/HTML 报告生成
│   │   ├── pdf_converter.py     # Markdown → PDF 转换 (pandoc + xelatex)
│   │   ├── md_to_pdf_katex.py   # Markdown → PDF (KaTeX + cloakbrowser, 支持 \(\)/\[\] 公式)
│   │   └── email_sender.py      # SMTP 邮件发送
│   └── pipeline/                # 流水线编排 (从 main.py 拆分)
│       ├── base.py              # 共享上下文 (SCRAPER_MAP, create_scraper, journal override 工具)
│       ├── phase_a.py           # Phase A 双源发现 (RSS + CrossRef 并行)
│       ├── phase_b.py ~ phase_h.py  # 各阶段独立模块
│       └── runner.py            # 编排器 (全跑/选择性跑)
│   └── web/                     # Web UI (FastAPI)
│       ├── app.py               # FastAPI 应用 + 路由
│       ├── templates/           # Jinja2 模板（只读 3 页面）
│       │   ├── base.html        #   布局模板
│       │   ├── dashboard.html   #   状态概览
│       │   ├── papers.html      #   论文浏览
│       │   └── report.html      #   报告阅览与下载
│       └── static/
│           ├── css/style.css
│           └── js/app.js
├── tools/                       # 辅助工具
│   ├── reset_pipeline.py        # 重置流水线状态（6 子命令 + --publisher 过滤）
│   ├── convert_reports_to_hugo.py  # Phase G 报告转 Hugo content + 部署
│   ├── fix_summary_formulas.py  # 批量 FormulaFixer 修复 LaTeX
│   ├── import_local_pdf.py      # 手动导入本地 PDF 到 MinerU 队列
│   ├── preview_report.py        # 预览报告生成（不标记数据库，可选 all/week/today 范围）
│   ├── schedule_daily.py        # 每日调度入口（A→F，支持 --no-reset-* 开关）
│   ├── schedule_weekly.py       # 每周调度入口（G→H）
└── README.md                    # 项目说明（面向访客/潜在用户）
```

# 数据模型

所有数据源模块统一使用 `src/common.py` 中的 `Paper` dataclass：

```python
@dataclass
class Paper:
    doi: str | None = None
    title: str | None = None
    date: str | None = None
    journal: str | None = None
    abstract: str | None = None
    authors: List[str] | None = None
    pdf_url: str | None = None
    url: str | None = None     # page link / canonical url
```

- **RSS** (`sources/rss.py`) — 返回 `list[Paper]`
- **CrossRef** (`sources/crossref.py`) — 使用独立的 `PaperMetadata` dataclass（更多字段，含 raw 原始数据）
- **Publisher** (`sources/publisher.py`) — 返回 `Paper`

# 共享异常体系

`src/common.py` 定义跨模块共享的异常，避免重复定义：

| 异常 | 用途 |
|------|------|
| `LLMConfigurationError` | API Key/URL 缺失或无效 |
| `LLMAPICallError` | 网络请求失败（超时、连接错误、HTTP 4xx/5xx） |
| `LLMResponseParseError` | API 响应结构异常（缺少字段） |
| `LLMContextLengthExceed` | 文本超模型上下文窗口 |

各模块特有的异常（如 `PageParseError`、`NonResearchPageError`、`NotFoundError`）保留在各自模块中。

# 流水线架构

整个项目以 SQLite 数据库为中心，按 9 个阶段顺序执行。每个阶段读取上一阶段的输出，处理后写入数据库。

```
Phase A: 双源发现 (RSS + CrossRef 并行)
  ├─ A-RSS:  RSS Feed 抓取 → 发现论文 → 写入 DOI/标题/链接
  └─ A-CR:   CrossRef 期刊查询 → ISSN+日期范围 → 写入 DOI/标题/链接
                      │  两路结果按 DOI 去重合并
                      ▼
Phase B: CrossRef 元数据
      │  补充作者 / 出版日期 / 期刊名 / 摘要
      ▼
Phase C: Publisher 页面 (cloakbrowser)
      │  爬取摘要 / PDF 链接 (绕过 Cloudflare)
      ▼
Phase E: 标题/摘要相关性初筛（OpenAI 兼容 LLM API）
      │  A/B/C + 低置信 D 进入正文候选；高/中置信 D 终止
      ▼
Phase E2: 限额 PDF 下载与 MinerU 全文解析
      │  每日总尝试 ≤ 3、单出版社 ≤ 2，失败也占额
      ▼
Phase E3: 正文相关性终审（OpenAI 兼容 LLM API）
      │  终审 A/B 进入下游；C/D 终止
      ▼
Phase F: LLM 论文总结（OpenAI 兼容 LLM API）
      │  生成结构化总结 (优先用 MinerU 全文, 无全文则跳过)
      ▼
Phase G: 报告生成
        │  Markdown 格式输出
        │  自动模式: 写入 auto/ 目录, 标记已报告
        │  用户模式: 写入 user/ 目录, 不标记已报告
      ▼
Phase H: 邮件推送
        │  SMTP 发送报告给团队成员
        │  有今日报告 → 作为附件发送
        │  无今日报告 → 发送无更新通知
```

# 数据库 Schema

单表 `papers`，每篇论文一行，按阶段添加字段。每个阶段有三态状态列（status + error + date）：

```
  ┌──────────────────────────────────────────────────────────────┐
  │                          papers 表                           │
  ├──────────────────────────────────────────────────────────────┤
  │  核心标识: id, doi (UNIQUE)                                  │
  │  基础元数据: title, abstract, journal, publisher,            │
  │             paperdate_rss/crossref/page, authors_json,       │
  │             page_url, pdf_url                                │
  │  发现来源:  discovery_source (rss / crossref / rss,crossref) │
  │                                                              │
  │  流水线状态 (每阶段 status + error + date 三列):             │
  │    Phase B: cr_metadata_fetched_*  → CrossRef 元数据         │
  │    Phase C: publisher_page_fetched_* → 期刊页面              │
  │    Phase E: relevance_screen_*      → 标题/摘要初筛          │
  │    Phase E2: mineru_parse_*         → MinerU PDF            │
  │    Phase E3: llm_relevance_*        → 正文相关性终审         │
  │    Phase F: llm_summary_*           → LLM 总结              │
  │    Phase G: report_*                → 报告状态              │
  │                                                              │
  │  时间戳: created_date, updated_date                          │
  └──────────────────────────────────────────────────────────────┘
```

**基础信息** (Phase A)
- `doi`, `title`, `page_url`, `journal`, `publisher`, `paperdate_rss`

**CrossRef 元数据** (Phase B) — 三列：`cr_metadata_fetched_status` / `_error` / `_date`
- `authors_json`, `paperdate_crossref`, `abstract`
- `abstract` 可由 Phase B 或 Phase C 写入，`CASE WHEN` 防止空值覆盖

**Publisher 页面** (Phase C) — 三列：`publisher_page_fetched_status` / `_error` / `_date`
- `paperdate_page`, `pdf_url`

**相关性初筛** (Phase E)
- `relevance_screen_status` / `_error` / `_date`
- `relevance_screen_category`, `_subfields`, `_confidence`, `_reason`
- `relevance_screen_is_backfill` — `0` 为新论文，`1` 为历史回填；下载队列优先新论文

**LLM 相关性终审** (Phase E3) — 三列：`llm_relevance_status` / `_error` / `_date`
- `llm_relevance_category` (TEXT: A/B/C/D) — 四级分类，替代已废弃的 `llm_relevance_result`
- `llm_relevance_subfields` (TEXT: JSON 数组) — 匹配的子领域列表
- `llm_relevance_confidence`, `llm_relevance_reason`
- `llm_relevance_basis` — `fulltext` / `abstract_clear_reject`。其中
  `llm_relevance_status='success' AND llm_relevance_basis='fulltext'` 是
  Phase E3 正文复检完成的明确标志；仅该组合的 A/B 才可进入报告。
- `llm_relevance_result` (INTEGER, **已废弃**) — 旧版二分类 0/1，`reset-relevance --all` 后不再写入

**MinerU 全文** (Phase E2) — 三列：`mineru_parse_status` / `_error` / `_date`
- `mineru_output_dir` — 解析输出目录相对路径（如 `data/mineru_output/10_1103_xxx/`）
- `mineru_fulltext` — 已废弃，不再写入。Phase F 直接从 `mineru_output_dir/full.md` 读取全文

**下载配额审计** — 独立表 `fulltext_download_events`
- 记录 `doi`, `publisher`, `local_date`, `attempted_at`, `status`, `error`
- 用 `BEGIN IMMEDIATE` 原子占位，按 Asia/Shanghai 自然日限制总尝试 3 篇、单 publisher 2 篇；失败占额且同一 DOI 当日最多尝试一次

**LLM 总结** (Phase F) — 三列：`llm_summary_status` / `_error` / `_date`
- `llm_summary_result` (JSON 字符串)

**报告状态** (Phase G) — 两列：`report_status` / `report_date`
- `report_date` 是主要过滤条件：`get_papers_for_report()` 使用 `report_date IS NULL` 查询未报告论文
- `report_status` 保留为辅助标记，`mark_papers_reported()` 同时写入两者
- 支持 `reset-report --days N` 按日期范围重置，方便同一天重试
- **显式 relevance 过滤（2026-07-25）**：除 `report_date IS NULL` 外，`get_papers_for_report()` 还要求 `llm_relevance_category IN ('A','B')` + `llm_relevance_status='success'`，且 `phase_g.py` 用户模式 SQL 同步加入。`update_llm_relevance()` **不重置** `llm_summary_*` 字段，必须由查询层显式拦截，否则「已总结但被重判为 C/D」的论文会被误入报（覆盖真实判定）。

**时间戳** (全局)
- `created_date`, `updated_date`

**状态值**：`FetchStatus` 枚举 (`pending` → `success` / `failed` / `skipped`)

### 邮件收件人配置 (email.yaml)

收件人列表存储在 `data/email.yaml`，格式为 `recipients` 数组，每项含 `email`、`name`（可选）、`enabled`（默认 `true`）：

```yaml
recipients:
  - email: user1@example.com
    name: "User 1"
    enabled: true
  - email: user2@example.com
    name: "User 2"
    enabled: false
```

Phase H（邮件推送）优先读取此文件（过滤 `enabled=true`），文件不存在或解析失败时回退到 `.env` 的 `SMTP_TO_ADDRS`。这是对原 `subscribers` 表（已移除）的替代方案——不再依赖 SQLite，纯 YAML 配置更易管理。

### skipped_dois 表（跳过/删除的论文 DOI）

```
skipped_dois:
  doi            TEXT PRIMARY KEY      -- 论文 DOI（唯一）
  reason         TEXT                  -- 跳过原因（如 NonResearchPageError）
  created_date   TEXT                  -- 记录时间
```

**用途**：记录被永久跳过（删除）的论文 DOI，防止流水线反复发现→删除→再发现的循环。
- NonResearchPageError（非研究文章）：写入 `skipped_dois` + 从 `papers` 删除
- AcceptedPaperError（接受前预发布）：仅从 `papers` 删除，**不**写入 `skipped_dois`（同 DOI 正式版会重新出现）
- Phase A 发现新论文前同时检查 `papers`（`paper_doi_exists`）和 `skipped_dois`（`is_doi_skipped`）

# 关键设计决策

## 1. Phase F 不全文回退

Phase F（LLM 总结）仅处理有 MinerU 全文的论文。无全文字段直接标记 `skipped`，**不**回退使用标题+摘要。原因：
- 摘要信息密度不足，LLM 总结质量不可控
- 避免「有总结但质量差」的误导性结果

## 2. Phase E/F 并发策略

使用 `ThreadPoolExecutor` + 共享 `LLM_CONCURRENT_MAX` 配置：
- 主线程负责 prompt 构建和 DB 写入（无网络 I/O）
- 子线程仅做纯 API 调用
- 单论文失败不影响整体流程（逐篇 try/except）

## 3. Publisher 爬虫的持续性上下文

使用 cloakbrowser 驱动 headful Chromium 和持久化 browser context：
- 同一 publisher 共用一个 session（`data/session_cached/<publisher>/`）
- cloakbrowser 自动处理浏览器指纹伪装，无需手动注入反检测 JS
- 失败熔断：连续失败 `PUBLISHER_MAX_CONSECUTIVE_FAILURES` 篇后自动中止，避免 IP 封禁

## 4. Phase E2 PDF 下载策略

`BasePublisherScraper.download_pdf()` 负责 PDF 下载（详见「流水线子阶段详解」）：
- 先 `goto(page_url)` 建立浏览器上下文（cookie/session/referrer）
- 仅 APS 扫描 DOM 中 `<a>PDF</a>` 提取同域 URL（解决 APS 跨域问题，2026-08-01 起门控）
- 先尝试 `requests` + 浏览器 cookies/UA 下载（最快，避免 AIP 等 CSP 拦截）
- 失败则降级为 `context.request.get()`（继承代理/cookie，解决 Optica 内联渲染场景）
- 下载后**立即保存**到 `data/mineru_output/<safe_doi>/paper.pdf`，再传给 MinerU 解析
- 保存前校验 `%PDF-` 头部，非 PDF 内容直接报错

**关键设计**：PDF 先保存再解析，确保 MinerU 上传失败时 PDF 不丢失。不再使用 tempfile。

## 5. 逐阶段错误隔离

每个阶段用独立 `try/except` 包裹单篇论文的处理。一篇失败不影响同阶段其他论文，一阶段失败不影响后续阶段（依赖的数据为空则后续阶段自然跳过）。

## 6. 数据库驱动的状态机

流水线不依赖内存状态，所有进度持久化到 SQLite：
- 中断后重启自动从断点继续
- `MAX_PAPERS_PER_PHASE` 支持单阶段调试
- `reset_pipeline.py` 提供精细化的状态重置（支持按 publisher 过滤）

## 7. 共享数据模型（src/common.py）

跨模块共享的 `Paper` dataclass 和 LLM 异常集中在 `src/common.py`，避免循环导入和重复定义：
- `Paper` 被 RSS 和 Publisher 同时使用
- LLM 异常被 `PaperRelevanceChecker` 和 `DeepSeekPaperSummarizer` 共享
- 各模块特有的异常（`PageParseError`、`NotFoundError`）保留在各自模块

## 8. 自动报告与用户报告分离

自动流水线生成的日报（Phase G）和 Web UI 用户勾选生成的报告写入不同目录，避免邮件推送误发用户报告：

| 维度 | 自动报告 (Phase G) | 用户报告 (Web UI) |
|------|-------------------|-------------------|
| 输出目录 | `data/reports/auto/` | `data/reports/user/` |
| 文件名 | `report_YYYYMMDD.md`（同日期覆盖） | `report_YYYYMMDD_HHMMSS.md`（不覆盖） |
| 标记已报告 | 是 | **否** |
| 邮件推送 | 是（Phase H 读取 `auto/`） | 否 |

Phase H 检测逻辑：
1. 若有 `report_path` 参数（CLI 指定报告）→ 直接发送指定报告，无更新通知模式禁用
2. 否则检查 `auto/report_YYYYMMDD.md` 是否存在
3. 存在 → 作为附件发送，正文使用 HTML 模板渲染
4. 不存在 → 发送无更新通知（同样使用 HTML 模板）

**报告论文数量统计**：使用 `re.findall(r'(?m)^## (?!目录)[^#]', ...)` 精确匹配报告中的 `## ` 标题行，排除 `### ` 子节和 `## 目录`（TOC 标题），避免 `str.count("## ")` 的误计。

**HTML 邮件模板**：`templates/email/default.html`（正式风格）、`templates/email/funny.html`（搞笑风格）和 `templates/email/detailed.html`（详细版，含追踪期刊、筛选依据、Publisher 抓取状态）
- 使用 `str.format()` 渲染，不引入新依赖
- 模板变量：`{report_title}`（邮件标题）、`{paper_msg}`（论文数量或无新增提示）、`{attachment_section}`（附件标记 HTML，无论文时为空）、`{journal_list}`（追踪期刊列表 HTML）、`{keyword_list}`（关键词标签云 HTML）、`{domain_block}`（完整领域定义 HTML）、`{publisher_stats}`（Publisher 抓取状态表 HTML）
- 报告作为附件，正文无论文列表
- 模板名可在 `configs/settings.yaml` 的 `email.template` 配置；若存在 `DATA_DIR/email_template_override.txt`，则使用其中的模板名覆盖
- `{paper_list}`（详细版模板专属）— 逐论文 Markdown 渲染，按期刊+日期排序，含元信息行（作者、期刊、DOI、匹配子领域等）

**Publisher 抓取状态**（`detailed.html` 特有）：显示过去 7 天各 publisher 的爬取健康状况。
- 仅展示 `publishers.yaml` 中至少有一个期刊 `enabled: true` 的 publisher（禁用 publisher 如 Optica 不显示）
- 状态判断：失败数 ≥ `PUBLISHER_MAX_CONSECUTIVE_FAILURES`（默认 3）→ "🚫 Blocked"，否则 "✅ OK"
- `pending` 论文是熔断器残留（Phase C 同 publisher 连续失败 N 篇后自动中止），不纳入统计

### 报告元信息增强（2026-06-15）

Markdown/HTML 报告**当前**显示在每篇论文标题下方的元信息行（2026-07-25 调整后顺序）：
- `**期刊**: {journal}` — 发表期刊名（如 Nature Physics）
- `**作者**: {authors}` — 论文作者列表
- `**日期**: {date}` — 论文发表日期（按 CrossRef / Page / RSS 优先级取）
- `**DOI**: [{doi}](https://doi.org/{doi})` — DOI 链接
- `**页面**: [链接]({page_url})` — 出版商页面
- `**相关性等级**: {category}` — LLM 判定的四级分类（A/B/C/D，Phase E 输出）
- `**判断理由**: {reason}` — LLM 给出相关 / 不相关的简要理由
- `**原文摘要**: {abstract}` — 论文原始摘要
- `**一句话**: {one_sentence}` — LLM 的一句话总结

随后是 4 个 H3 子节，顺序与文本保持不变：研究动机与目标 / 关键方法与设置 / 主要结果与物理内涵 / 要点总结。

`relevance_category` 与 `relevance_reason` 来自 `llm_relevance_category` / `llm_relevance_reason` DB 列（Phase E 输出），`reason` 是 LLM 自由文本，统一通过 `_process_results_markdown()` 处理（LaTeX 公式修复 + 字面量换行转换 + 内部标题重定级），与 `motivation` / `method` 等 LLM 总结字段保持一致的安全渲染。

**2026-07-25 调整**：
- **删除** `**出版社**`（与 `**期刊**` 信息重叠，保留更具体的期刊名足矣）
- **删除** `**相关方向**`（LLM 子领域匹配过宽/不够准确，`**判断理由**` 已能说明问题）
- **删除** `**PDF**`（Markdown/邮件内 PDF 链接点击率低，DOI + 页面足够回溯）
- **重排顺序**：`期刊 → 作者 → 日期 → DOI → 页面 → 相关性等级 → 判断理由 → 原文摘要 → 一句话`

**报告头部图例（2026-07-25）**：为让读者在看到「相关性等级」字段时能立即理解 A/B/C/D 的判定标准，报告开头插入相关性等级图例（Markdown `>` 引用块 / HTML `<blockquote class="relevance-legend">`），转写自 `configs/prompts/relevance.yaml` 中 Phase E LLM Prompt 的权威定义。生成入口在 `paper_report_generator.py` 的 `_relevance_legend_md()` / `_relevance_legend_html()`，分别由 `generate_markdown()` / `generate_html()` 调用。**用户反馈后简化**：图例不再标注 `configs/prompts/relevance.yaml` 来源路径，仅保留 A/B/C/D 简表。

**报告排序说明（2026-07-25 新增）**：报告最顶端（在相关性图例之前）插入一行「报告排序」说明（Markdown `>` 引用块 / HTML `<blockquote class="sort-note">`），告知读者排序规则（按相关性等级 A→B→C→D、同级内日期倒序）。该说明文本与 `_sort_papers()` 实际行为一致，模板位于 `templates/report/{markdown,html}/sort_note.{md,html}.j2`，可由用户自行编辑。

**报告其他说明（2026-07-25 新增）**：图例之后插入「其他说明」块（Markdown `>` 引用块 / HTML `<blockquote class="disclaimers">`），列 3 条局限性提示帮助读者正确解读报告收录与排序：
- 筛选 prompt 调整后，部分历史文献可能被重新召回，使单次报告收录量明显增加。
- RSS 历史回溯可能纳入较早发表（数月甚至数年前）的文献。
- 相关性判定受 prompt 表述、LLM 能力上限及仅以摘要为输入的信息局限影响，结果可能存在偏差，请结合论文全文进一步判断。

模板位于 `templates/report/{markdown,html}/disclaimers.{md,html}.j2`，可由用户自行编辑。CSS：淡橙底 + 橙色左竖线，与 `sort-note`（黄）和 `relevance-legend`（蓝）形成三色区分：蓝=图例（结构）、黄=排序（流程）、橙=说明（解读）。

**报告排序**（2026-07-25 改）：`paper_report_generator._sort_papers()` 用稳定 sort 实现「相关性等级 A 先 → 同级日期倒序（最新在前）」：
- 一级 key：`relevance_category` 经 `_RELEVANCE_RANK = {"A":0, "B":1, "C":2, "D":3}` 映射升序（未知值 rank=99 排末位）
- 二级 key：`date` 字符串倒序；ISO `YYYY-MM-DD` 字符串字典序 ≡ 时间序，无需 datetime 解析
- 实现技巧：先 `sort(date, reverse=True)` 再 `sort(category)`，利用 Python 排序稳定性
- 由 `generate_markdown()` / `generate_html()` 在最顶端调用，auto + user 两种模式都受益；`phase_g.py` 的旧 `paper_list.sort(...)` 已删除

### 报告解释页（2026-07-26 新增，2026-07-25 大幅简化）

每期 Phase G 生成 Markdown/HTML 报告后，额外生成一份独立 HTML 解释页 `report_YYYYMMDD_explained.html`，帮助读者理解「为什么这篇论文被 LLM 判为 A/B 相关」。

- **模板文件**：`templates/report/html/explained.html.j2`
- **渲染环境**：复用 `src/processors/paper_report_generator.py:_get_template_env()` 创建的 Jinja2 Environment（`FileSystemLoader` 指向 `templates/report/`），不引入新的 Environment。
- **输出要求**：单文件自包含 HTML，无外部 `<link>` / `<script>` / CDN / Google Fonts；全部 CSS 内联在 `<style>` 中；字体使用系统栈。
- **页面结构（2026-07-25 大幅简化后）**：
  1. Header：标题「报告解释 · {{ date_str }}」+ 副标题「本期论文推送的判定依据与 Prompt 快照」。
  2. 完整 Prompt 快照：两个 `<details>` 折叠区，Phase E 相关性判断默认展开，Phase F 论文总结默认折叠，均用 `<pre>` 保留源码（含 LaTeX）不渲染。
  3. Footer：生成时间 + 项目名。
- **模板变量**（2026-07-25 简化后）：`date_str`、`relevance_prompt`、`summary_prompt`、`generated_at`（仅 4 个，原 10 个中的 6 个 stats/chart 变量删除）。
- **2026-07-25 简化历史**：
  - 1st pass：删阶段状态柱状图 + 近 7 天采集柱状图 + `phase_status` / `weekly` / `phases_count` 数据收集。
  - 2nd pass：删 stats grid（总论文 / 待报告 / 出版社 3 个 stat-card）+ `total_papers` / `pending_report` / `publishers_count` 数据收集。用户认为「没人关注这些数字」，解释页只保留最有价值的 Prompt 快照。
- **Prompt 安全渲染**：因 Environment 配置 `autoescape=False`，模板内对 `relevance_prompt` / `summary_prompt` 显式使用 `| e` 过滤，防止 `<` / `>` 等字符破坏 HTML。

## 10. LLM 总结输出简单化

LLM 总结（Phase F）的输出必须限制为简单 LaTeX，禁止复杂环境。

## 11. 双源发现机制（RSS + CrossRef 并行）

Phase A 从单一路径（RSS）拆为双路径并行，解决 RSS 完整性不可控和无法回溯时间跨度的问题。

### 两路分工

| 路径 | 标识 | 方法 | 数据范围 | SKIP 开关 |
|------|------|------|---------|----------|
| RSS 发现 | A-RSS | `parse_rss()` 解析 Feed XML | RSS Feed 最新 N 篇 | `SKIP_PHASE_A_RSS` |
| CrossRef 查询 | A-CR | `fetch_by_journal()` 按 ISSN+日期 | CrossRef 索引全量论文 | `SKIP_PHASE_A_CR` |

两路独立运行，按 DOI 去重合并，互不阻塞。

**DOI 归一化**（2026-08-09）：DOI 规范本身大小写不敏感，但 RSS 源（如 Optica 给大写 `10.1364/OE.605615`）
与 CrossRef API（统一小写）大小写不一致，若去重键未归一化会双插同论文副本。现已：
- 所有插入路径（`insert_rss_basicinfo` / `insert_paper_basicinfo` / `insert_skipped_doi`）入参 `doi.lower()`
- 所有 DOI 匹配（`paper_doi_exists` / `is_doi_skipped` / `append_discovery_source` / `insert_paper_created_date`）
  使用 `LOWER(doi)=LOWER(?)` 大小写不敏感
- 存量数据迁移工具 `tools/dedup_doi_case.py`：按 `lower(doi)` 分组，成对行按进度保留更完整者并合并
  `discovery_source`，单例行统一小写（`--dry-run` 预览 + 交互确认）。2026-08-09 迁移：560 组去重、
  154 单例小写化、8815 → 8255 行。

### 来源标注列 `discovery_source`

每篇论文都记录它的发现来源，方便调试和评估数据源质量：

| discovery_source 值 | 含义 |
|--------------------|------|
| `rss` | 仅 RSS 发现 |
| `crossref` | 仅 CrossRef 发现 |
| `rss,crossref` | 两路都发现了这篇 |

通过 SQL 聚合可以直观量化 RSS 的遗漏率：
```sql
SELECT discovery_source, COUNT(*) FROM papers GROUP BY discovery_source;
```

### A-CR 核心链路

`CrossrefClient.fetch_by_journal()` 使用 CrossRef `/journals/{issn}/works` 端点：
- **过滤**：`type=journal-article` 排除 editorial/correction；`from-pub-date` / `until-pub-date` 定位时间窗口
- **翻页**：offset 模式（0/100/200...），页间 0.2s 礼貌间隔，上限约 10000 条
- **输入**：期刊 ISSN + 起止日期
- **输出**：`list[PaperMetadata]`（含 doi/title/date/journal/publisher/url 等）

### 为什么选择 CrossRef 而非其他

| 候选源 | 选择理由 | 不选理由 |
|--------|---------|---------|
| **CrossRef** ✅ | 已在 Phase B 使用同一 API；无需额外密钥；覆盖全部 22 个期刊；支持日期范围和文章类型过滤 | — |
| OpenAlex | 更丰富的元数据（含引用关系） | 新依赖，当前无此需求 |
| 出版社自有 API | 数据最权威 | 每家 API 不同，维护成本高 |

### 关键设计

1. **增量模式统一**：A-CR 默认只查过去 1 天（`CROSSREF_LOOKBACK_DAYS=1`），与 RSS 的"每日最新"语义一致
2. **不强制 ISSN**：期刊的 ISSN 字段为可选配置，无 ISSN 的期刊仅走 RSS 路径
3. **附录操作**：`append_discovery_source()` 使用逗号分隔、不重复的语义，未来新增数据源（如 OpenAlex、PubMed）只需追加字符串即可，无需改 schema

### 11b. CrossRef 智能回溯（故障补漏）

**动机**：A-CR 默认回溯 1 天。若某次 cron 因机器故障/网络问题/手动跳过而漏跑，仅靠 RSS 抓取可能遗漏当日的若干论文（RSS Feed 不一定完整且无回溯能力）。下次再跑 A-CR 时已"翻篇"，那 1 天的论文就永久丢失。

**解决**：基于 `data/state/last_run.json`（gitignored）记录上次成功运行日期，下次运行时按"缺口天数"自动扩展回溯窗口，封顶 `CROSSREF_LOOKBACK_DAYS_MAX`（默认 7 天）。

**决策公式**：

```
actual_lookback = max(CROSSREF_LOOKBACK_DAYS, today - last_successful_run)
actual_lookback = min(actual_lookback, CROSSREF_LOOKBACK_DAYS_MAX)
```

| 场景 | last_run 距今 | 实际回溯 | 说明 |
|------|--------------|---------|------|
| 首次运行 | 无记录 | `CROSSREF_LOOKBACK_DAYS` (1) | 保守起步 |
| 日常运行 | 0~1 天 | `CROSSREF_LOOKBACK_DAYS` (1) | 零额外开销 |
| 故障 1 天 | 2 天 | 2 天 | 自动补漏 |
| 故障 5 天 | 5 天 | 5 天 | 自动补漏 |
| 故障 10 天 | 10 天 | `CROSSREF_LOOKBACK_DAYS_MAX` (7) | 封顶，部分遗漏 |
| JSON 损坏 | — | `CROSSREF_LOOKBACK_DAYS` (1) | 降级为默认 |

**写入时机**：A-CR 阶段执行完所有期刊后（无论发现论文数量），调用 `_save_last_run_date(to_date)` 写入当日日期。**仅 A-CR 成功即更新**——RSS 故障不阻塞 CrossRef 补漏（两者独立）。

**实现要点**（`src/pipeline/phase_a.py`）：

- `_load_last_run_date()` — 读 JSON，损坏时返回 None + warning
- `_save_last_run_date()` — 原子写入（`.tmp` → `rename`），避免崩溃中途损坏
- `_compute_lookback_days()` — 决策函数，被 `phase_a_crossref` 调用
- 副作用：故障补漏日的 API 调用量约等于 (实际回溯 - 1) × 平时。7 天封顶下最坏情况为平时的 7 倍；正常 1 天轮询时无影响

**故障时长 > max 时的取舍**：超过 7 天的故障仍会漏检论文（与"每日增量轮询"语义本身不冲突）。如需覆盖更长窗口，手动调高 `crossref_lookback_days_max`；或在故障恢复后用 `python -m tools.manual_backfill`（未来工具，本次未实现）补拉。

**配置**（`configs/settings.yaml`）：

```yaml
pipeline:
  crossref_lookback_days: 1     # 日常回溯
  crossref_lookback_days_max: 7 # 故障补漏上限
```

这是贯穿 prompt 设计、FormulaFixer 和报告生成的全链路约束。

**禁止的 LaTeX 构造：**

| 构造 | 原因 |
|------|------|
| `\begin{}` / `\end{}`（cases, aligned, matrix, gathered 等） | 需要 amsmath 宏包，下游渲染器不一定支持 |
| `\\` 换行符 | JSON → Python → Markdown 多层转义后极易出错 |
| `&` 对齐标记 | 非标准 Markdown 字符，可能被意外解释 |

**允许的 LaTeX 构造：**

| 类别 | 命令 |
|------|------|
| 公式包裹 | `\(...\)` 行内，`\[...\]` 独立 |
| 基本命令 | `\frac` `\sqrt` `\int` `\sum` `\prod` `\partial` `\nabla` `\infty` |
| 希腊字母 | `\alpha` `\beta` `\gamma` `\delta` `\epsilon` 等 |
| 上下标 | `^` `_` 及花括号分组 |
| 简单文本 | `\text{}` `\mathrm{}` `\mathbf{}`（用于物理单位标注） |
| 运算符 | `\times` `\pm` `\approx` `\neq` `\leq` `\geq` `\rightarrow` 等 |

**设计依据：**

1. **多层转义脆弱性**：复杂环境中的 `\\` 和 `&` 经过 JSON 序列化（`\\\\`）→ Python 解码（`\\`）→ Markdown 渲染，每层都可能出错
2. **渲染环境不一致**：下游报告可能是 Markdown（GitHub 渲染）、HTML（pandoc --mathml）、PDF（cloakbrowser 打印），不同格式对复杂 LaTeX 支持程度不一
3. **FormulaFixer 能力边界**：FormulaFixer 仅做 `\(\)`/`\[\]` 包裹修复和 Unicode 转换，无法理解和修正 `\begin{}`/`\end{}` 环境级构造
4. **可预测性**：限制为基本命令后，LLM 输出格式稳定，FormulaFixer 可可靠修复，所有下游格式一致渲染

**实施方式**：`src/config.py` 中 `SUMMARIES_PROMPT` 的第 4 条规则明确禁止上述构造，LLM 在生成时即遵循约束。

# 配置数据模型

## publishers.yaml

```yaml
publishers:
  - id: nature              # 唯一标识
    name: Nature            # 显示名称
    publisher: nature       # 出版社 key (映射到 SCRAPER_MAP)
    rss: "https://..."      # RSS Feed URL
    enabled: true           # 是否启用
```

## keywords.yaml

使用结构化字典格式（`scope_definition` + `irrelevant_fields`）：

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
    - "Fusion: Tokamak, Stellarator, magnetic confinement fusion..."
    - "Space plasma: Solar wind, Magnetosphere..."
```

### 字段分工（三层职责不重叠）

| 字段 | 决策步骤 | 用途 | 语种 | 要求 |
|------|---------|------|------|------|
| `context_gates` | Step 1 | Phase E LLM prompt — **per-term 词义消歧** | 中文 | 跨子域的高歧义词汇判定规则（如 "plasma" 在 fusion vs 加速器语境）。负责 term-level 消歧，决定某 term 的某次出现是否算 in-scope |
| `irrelevant_fields` | Step 2 | Phase E LLM prompt — **topic-level 黑名单** | 中文 | "per-term 消歧抓不住、必须靠 topic 整篇匹配"的主题兜底。**只放 Step 1 覆盖不到的主题**；已被 context_gates 覆盖的（如 fusion plasma）不再重复 |
| `scope_definition` | Step 3 | Phase E LLM prompt — **正类子域分类** | 中文 | 每子域含 `description`（段落描述）+ `topics`（展开关键词列表），供 LLM 决定 A/B + sub-domain key |

**三步关系**：Step 1 解决"这个词是不是我们要的那个意思"；Step 2 解决"这篇文章整个主题是不是不在我们范围"；Step 3 解决"在范围内的话属于哪个子域、几级相关"。每步只做一件事，互不替代。`scope_definition` 的子域可独立注释，不关注的域直接 YAML 注释即可。

### Phase E Prompt 构建流程

```
keywords.yaml:
  context_gates      (Step 1 — per-term 词义消歧)
  irrelevant_fields  (Step 2 — topic-level 黑名单)
  scope_definition   (Step 3 — 正类子域)
          ↓
  src/config.py: build_scope_block()
    渲染顺序: Step 1 → Step 2 → Step 3
    标题前缀: "# Step 1: ...", "# Step 2: ...", "# Sub-Domain: ..."
          ↓
  Plain text block with ## headers + bullet lists
          ↓
  configs/prompts/relevance.yaml template (scope_block placeholder)
    决策树: (a) Context Gates → (b) Irrelevant Fields → (c) A/B/C/D → (d) sub-domain
          ↓
  LLM: classification task, JSON output
```

## .env

密钥与 SMTP 配置存储文件（不提交到仓库），通过 `python-dotenv` 加载：

```ini
CROSSREF_MAILTO=your_email@example.com
MINERU_TOKEN=your_mineru_token_here
DEEPSEEK_API_KEY=sk-your-deepseek-key

# SMTP 邮件推送（可选，不配置则跳过 Phase H）
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your_email@qq.com
SMTP_PASSWORD=your_auth_code
SMTP_FROM_ADDR=your_email@qq.com
SMTP_TO_ADDRS=colleague1@example.com,colleague2@example.com
```

`src/config.py` 通过 `os.getenv()` 读取，缺失时留空（对应功能跳过）。

# Web UI 架构

`src/web/` 模块提供基于 FastAPI 的 Web 控制面板。

## 定位

> **Web UI 是只读展示台（Dashboard + Report 阅览），不接受写入操作。** 所有配置修改走配置文件，所有运行控制走 `tools/run_pipeline.py`。Home / Pipeline / Logs 页面已在 2026-07-26 瘦身中删除。

| CLI 擅长 | Web UI 擅长 |
|----------|------------|
| 定时/自动化运行（cron） | 可视化监控：一眼看清各阶段状态分布 |
| ad-hoc 重置/调试（reset 工具） | 交互式报告：阅览、筛选、下载（marked + KaTeX + DOMPurify） |
| 深度调试（debug 脚本） | 3 卡片统计（论文总数/待报告/出版社）+ 阶段柱状图 + 7 天采集趋势 |
| 批量全流程 | 只读浏览（无控制按钮） |

## 页面功能

| 页面 | 路由 | 功能 |
|------|------|------|
| Dashboard | `GET /dashboard`（`/` 302 重定向至此） | 状态概览：3 统计卡片（论文总数 / Pending Report / 出版社数）；Pending Report 与 7 天 `reportable` 仅计入“正文终审为 A/B 且完整总结成功”的论文；Pipeline 各阶段状态柱状图（pending 在 UI 层合并到 skipped 显示，3 段柱状图）；**近 7 天采集趋势图（3 桶：reportable / total_failed / other，与 explained.html 设计一致）**；每 10s 自动刷新。 |
| Papers | `GET /papers?sort=created\|published\|summary&category=a\|b\|ab\|all&has_summary=0\|1&page=N&per_page=50\|100\|200` | **只读浏览**：三种排序（入库/发表/LLM 总结生成时间）、四类筛选（A/B/AB/All）、`has_summary` 筛选可报告论文；**分页**：底部分页器 `共 M 篇 · 第 N/T 页 · [每页 K ▾] [‹ 上一页] [下一页 ›]`，per_page 白名单 50/100/200。无 checkbox 选取、无生成按钮 |
| Report | `GET /report?show=<filename>` | **报告档案馆**，仅查看不编辑。顶部下拉选择器按 `mtime DESC` 列出所有报告（每条：日期切片/来源/论文数/相对时间，auto + user 混排），主区渲染选中报告（marked + KaTeX + DOMPurify 反 XSS）；下载链接常驻右侧 |

## WebUI 安全

WebUI 已降级为纯只读前端（无 POST 端点），并实施以下安全加固：

| 编号 | 措施 | 说明 |
|------|------|------|
| R1 | 路径遍历防护 | `/report/data/{filename}` 和 `/report/download/{filename}` 使用 `Path.resolve()` + `relative_to()` 确认目标仍在报告目录内，防止 `../../etc/passwd` 与同前缀兄弟目录逃逸 |
| R2 | DOMPurify XSS 过滤 | `report.html` 中 `marked.parse()` 输出经 `DOMPurify.sanitize()` 净化，仅保留 `target` 属性（链接 `_blank` 必须），CDN 同源（cdnjs） |
| R4 | 安全响应头 | `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: strict-origin-when-cross-origin`、`Permissions-Policy: geolocation=(), microphone=(), camera=()` |

**Remaining risks（建议在生产部署前处理）**：
- 建议用 **nginx 反代** 统一管理 TLS 证书 + 限速 + Basic Auth
- 用 **防火墙/安全组** 限制访问源 IP（192.168.0.0/16 等）
- **暂不上公网** — 该 UI 为内网工具设计；如需公网访问，务请前置 nginx 并配置 CSP + HSTS

### 启动方式

```bash
# 内网最小暴露：仅监听本地，由 Nginx 反代 + Basic Auth 对外
PYTHONPATH=src uvicorn src.web.app:app --host 127.0.0.1 --port 8080

# 桌面开发
PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080

# 无头服务器（Phase C 需要 Xvfb 虚拟显示）
xvfb-run -a bash -c 'PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080'
```

# 阶段开关（SKIP_PHASE）

所有阶段可通过 `src/config.py` 中的 `SKIP_PHASE_*` 独立开关：

```python
SKIP_PHASE_A_RSS = False
SKIP_PHASE_A_CR = False
SKIP_PHASE_B = False
...
```

**配置隔离规则：**

| 配置源 | 影响范围 | 说明 |
|--------|---------|------|
| `src/config.py` 的 `SKIP_PHASE_*` | CLI (`python src/main.py`) | CLI 默认值，Web UI 不读取 |

配套 `MAX_PAPERS_PER_PHASE` 控制每阶段处理上限（0 = 不限制），该限制对 CLI 和 Web UI 均生效。

## journal_overrides.json

`data/journal_overrides.json` 存储 Data Sources 页面的期刊启用/禁用偏好：

```json
{
  "journals": {
    "nature": { "enabled": true, "rss_enabled": true, "cr_enabled": true },
    "nphys": { "enabled": false }
  }
}
```

- 缺失的 journal id → 回退到 `publishers.yaml` 的 `enabled` 字段
- `rss_enabled` / `cr_enabled` 缺失 → 回退到对应 journal 的 `enabled` 值

# 错误处理与韧性策略

## 1. 逐论文错误隔离

每个阶段用独立 `try/except` 包裹单篇论文的处理。一篇失败不影响同阶段其他论文，一阶段失败不影响后续阶段。

## 2. Phase C 重试机制

`phase_c_publisher()` 中对每篇论文最多尝试 3 次（`pipeline/phase_c.py`）：

| 尝试 | timeout | 冷却 | 条件 |
|------|---------|------|------|
| 第 1 次 | 5000ms | 0 | 首次加载 |
| 第 2 次 | 15000ms | 0 | 第 1 次失败 |
| 第 3 次 | 45000ms | 120-180s 随机 | 第 2 次失败 |

`NonResearchPageError` 不重试（非论文页面重试结果不变）。`consecutive_failures` 只在全部尝试都失败后递增。

## 3. LLM API 重试

`call_llm_api_with_retry()` (`src/common.py`) 是共用封装。对 429/5xx、网络错误与 HTTP 200 但缺少 `choices` 的服务端错误载荷，采用可配置的指数退避（默认最多 3 次）并计入每阶段熔断器；连续 5 次瞬态失败后不再发起新的外部请求，未执行任务保留 `pending` 等待下一日自动重试。401/402、请求格式和内容 JSON 错误不计入熔断。所有 LLM 调用（Phase E 相关性、Phase F 总结、FormulaFixer）统一使用。

LLM 服务地址由 `configs/settings.yaml` 的 `llm.base_url` 控制，默认
`https://api.deepseek.com`。`src/common.py:build_chat_completions_url()` 仅接受绝对 HTTP(S)
基础地址，保留其中的版本路径（例如 `/v1`），并统一追加 `/chat/completions` 后传给三个
LLM 调用方。因此可切换到任意 OpenAI Chat Completions 兼容网关（包括 OpenCode Go），而无需修改
处理器代码；网关切换时仍须由使用者调整对应的模型名与 API Key。

RSS 与 Nature 的 requests HTTP 回退使用 `trust_env=False` 的专用 Session，避免桌面代理环境变量导致代理出口返回 406；需要代理的出版商必须通过 `publisher.proxy` 显式配置。

## 3b. CrossRef journal 查询重试

`fetch_by_journal()`（Phase A-CR 使用）增加 3 次指数退避重试（与 `fetch_by_doi` 一致），避免一次网络抖动丢失当日全期刊数据。

## 3c. RSS Feed 抓取重试

`RSSProcessor.fetch_rss()` 增加 3 次指数退避重试，防止临时 DNS/503 导致单期刊数据丢失。

## 3d. MinerU API 全流程重试

`MinerUParser._request_with_retry()` 提供统一的 3 次重试封装，覆盖 create_batch / poll / download 三个步骤。

**注意**：`_upload_file()` 不使用 `_request_with_retry()`，因为 OSS 预签名 URL 对 Content-Type 敏感。`self._session` 默认带 `Content-Type: application/json`，会导致 OSS 签名校验失败（403 Forbidden）。严格遵循 [MinerU 官方文档](https://mineru.net/api/v4/file-urls/batch) 的说明（"No Content-Type header is required when uploading files"），上传使用 module-level `requests.put(url, data=data)`，不经过 session，不设自定义 Content-Type——requests 对二进制 `data` 自动使用 `application/octet-stream`，匹配 OSS 预签名。同时 upload 自身也包含 3 次指数退避重试。

## 4. JSON 反斜杠修复（双层防御）

LLM 输出的 JSON 字符串中 LaTeX 反斜杠未正确转义是常见问题。代码包含两层防御：

**第一层** — API 重试循环内（`call_deepseek_api`）：
```
API 返回 → json.loads() 验证 → 失败则 re.sub 修复 → 修复后重试 json.loads() → 仍失败则抛异常重试 API
```

**第二层** — Phase E/F 主线程（`pipeline/phase_e.py`, `pipeline/phase_f.py`）：
```
future.result() → re.sub(r'(?<!\\)\\(?![\\"/bfnrtu])', r'\\\\', result_str) → json.loads() → 写入 DB
```

正则 `(?<!\\)\\(?![\\"/bfnrtu])` 含义：匹配前面没有反斜杠、后面也不是合法 JSON 转义字符的反斜杠，将其加倍。

## 5. 空摘要保护

`update_publisher_page()` 的 SQL 使用 `CASE WHEN`：
```sql
abstract = CASE WHEN ? != '' THEN ? ELSE abstract END
```
防止 Phase C 的空摘要字符串覆盖 Phase B 已写入的有效摘要。

历史空摘要记录可通过 `tools/reset_pipeline.py reset-crossref --empty-abstract` 或
`reset-publisher --empty-abstract` 重置对应的上游阶段后重新处理。

## 6. SMTP 重试与连接加固

`EmailSender.send()` (`src/processors/email_sender.py`) 含 1 次自动重试（共 2 次尝试），间隔 2s：

| 尝试 | 行为 |
|------|------|
| 第 1 次 | 正常连接 |
| 第 2 次 | sleep(2) 后重试，失败则抛最后一次异常 |

额外保护措施：
- 连接代码包裹在 `try/except` 内，`SMTPServerDisconnected` 等异常被捕获后触发重试
- TLS 模式下 STARTTLS 后显式调用 `ehlo()` 重新协商加密通道能力（RFC 3207）
- `finally` 中 `server.quit()` 以 `try/except` 保护，且先判断 `server is not None`

## 7. 非论文页面检测（NonResearchPageError）

某些 RSS 抓取的条目不是研究论文（Erratum、Publisher's Note、Comment on、Response to 等），
这类页面在 Publisher 抓取阶段（Phase C）能正常加载，但缺少有效摘要。

### 检测策略

Phase C 采用两级检测：

**一级 — Scraper 元数据检测**（精确，依赖 publisher HTML 结构）：
| Scraper | 检测依据 | 匹配值 |
|---------|---------|--------|
| NatureScraper | `<meta name="dc.type">` | `!= "OriginalPaper"` |
| ScienceScraper | `<meta name="dc.Type">` | `!= "research-article"` |

**二级 — Science 互补检测：altmetric_type**（覆盖 CrossRef 发现路径的非研究文章）：
- 条件：`meta[name="altmetric_type"]` 存在（值为 `news`、`blog` 等）
- 这类页面通常没有 `dc.Type` meta 标签（RSS 路径有，但 CrossRef 路径来的文章没有），
  因此一级的 dc.Type 检测对它们无效
- 实现位置：`ScienceScraper.parse_page()` 中，dc.Type 检测之前执行
- 对应 bug：Science 的 news 文章通过 CrossRef 入库后，Phase C 找不到 dc.Type 标签，
  报 `PageParseError` 而不是抛 `NonResearchPageError`，导致失败原因不清

**三级 — Science og:type 兜底**（覆盖既无 dc.Type 也无 altmetric_type 的非研究文章）：
- 条件：`dc.Type` 为空且 `altmetric_type` 不存在时，检查 `<meta property="og:type">`
- 这类页面（如 Careers / Working Life）有正常的 `og:type=article` 但缺少 dc.Type，
  说明页面加载成功但不属于有 dc.Type 注释的研究文章
- `og:type` 存在 → `NonResearchPageError`；两者均不存在 → `PageParseError`
- 实现位置：`ScienceScraper.parse_page()` 中，原 dc.Type 空值判断分支内

**四级 — 关键词 + 空摘要检测**（通用兜底，对所有 publisher 生效）：
- 条件：`abstract` 为空 `AND` 标题包含以下关键词之一
- 关键词表：`Erratum`, `Comment on`, `Response to`, `Publisher's Note`, `Announcement`
- 实现位置：`pipeline/phase_c.py` 的 retry 循环内，`parse_page()` 成功后检查

### 触发后的行为

NonResearchPageError 触发后，Phase C 会执行：
1. 写入 `skipped_dois` 表（记录 DOI + 原因 + 时间），防止将来被重新发现
2. 调用 `db.delete_paper()` 从 `papers` 表中删除该记录

这与 `AcceptedPaperError` 不同——Accepted Paper 仅删除不记入 `skipped_dois`，
因为同 DOI 的正式版论文会在未来出现，届时 Phase A 应能正常发现。

删除后论文在下次 RSS/CrossRef 发现时会被 `is_doi_skipped()` 阻止，不再重复处理。

### 与空摘要论文的区别

| 类型 | Phase C 行为 | Phase E 行为 |
|------|-------------|-------------|
| **非论文页**（Erratum 等） | 直接 `delete_paper()` 删除 | — |
| **合法空摘要论文**（短通讯、无摘要 OA） | 标记 `success`（abstract 为空） | 正常计算相似度 | `abstract` 为空时标记 `skipped` |
| **全空页**（CF 拦截、页面错误） | 标记 `failed`（retry 后仍失败） | 跳过（上游 failed 不影响，仅查自己状态） | 同上 |

合法空摘要论文与全空页的区别：前者有 title + doi，后者三项全空。

## 8. Nature 非研究文章过滤（SKIP_NATURE_NEWS）

**范围**：Nature 旗下期刊（Nature、Nature Physics、Nature Photonics、Nature Communications）的
RSS Feed 和 CrossRef 数据源中均可能包含非研究文章——News、News & Views、Comments、Editorials、
Research Briefings、Books & Arts、Obituaries、Careers、Podcasts 等。

**过滤依据**：Nature 使用 `d41586` DOI 前缀标识所有非研究内容（如 `10.1038/d41586-026-01741-z`），
而研究论文使用其他前缀（`s41586-`、`s41567-`、`s41566-`、`s41467-` 等）。因此 `SKIP_NATURE_NEWS`
通过检测 DOI 字符串中是否包含 `/d41586-` 来判断，而非逐个枚举文章类型。这种方式覆盖了 Nature 所有
非研究内容，且无需随 Nature 的文章类型变化而更新。

**双路径覆盖**：

| 数据源路径 | 过滤位置 | 实现 |
|-----------|---------|------|
| A-RSS（RSS） | `phase_a_rss()` | `if SKIP_NATURE_NEWS and "/d41586-" in paperDOI: continue` |
| A-CR（CrossRef） | `phase_a_crossref()` | `if SKIP_NATURE_NEWS and "/d41586-" in (paper.doi or ""): continue` |

**Config 开关**：`src/config.py` 中 `SKIP_NATURE_NEWS = True`（默认开启）。关闭后 Nature 新闻类文章
将进入流水线。不推荐关闭——非研究文章在 Phase B 会因为作者数据缺失而标记 failed，但仍会消耗 API 配额。

## 9. Accepted Paper 跳过（AcceptedPaperError）

### 9a. APS

**背景**：APS 在论文正式发表前会发布 Accepted Paper（预接受版本）。这类页面可通过 CrossRef 发现
（DOI 形如 `10.1103/27t3-61j2`），其访问 URL 路径含 `/accepted/`（例如
`https://journals.aps.org/prl/accepted/10.1103/27t3-61j2`）。

**页面特征**：
1. URL 路径含 `/accepted/`
2. HTML 中含有 `<ul class="flex justify-start"><li class="article-feature-tag">Accepted Paper</li></ul>`

**处理策略**：不为此类页面编写专用选择器。Accepted Paper 有摘要但页面结构与正式论文不同
（当前 `#abstract-section-content` 选择器无法提取 abstract），且不提供 PDF 链接。由于
无正文内容可供 MinerU 解析和 LLM 总结（Phase F 需要全文），整篇论文在 Phase C 阶段即被跳过。

**Phase C 行为**（`pipeline/phase_c.py`）：
1. `APSScraper.parse_page()` 检测到 Accepted Paper 特征 → 抛出 `AcceptedPaperError`
2. 捕获后标记 `publisher_page_fetched_status = 'skipped'`，error 信息：
   `"AcceptedPaper: no full text available"`
3. 级联跳过 Phase E
4. 后续阶段（Phase E2/F/G/H）自然跳过

### 9b. Optica

**背景**：与 APS 类似，Optica 在论文正式发表前也会发布 Accepted Paper（预接受页面）。
这类页面通过 CrossRef 发现后，Phase B（CrossRef 元数据）能获取到 title/authors/journal/date，
但 abstract 为空（CrossRef 不返回预发布文章的摘要）。当前 Optica 网站对 Accepted Paper
页面没有 Radware 保护（正式论文受 Radware Bot Manager 保护），约 77KB 的 HTML 可直接访问。
但页面中不包含有效摘要和 PDF 链接（无 `citation_pdf_url` meta 标签）。

**页面特征**：
- 核心标识：`#articleBody` 区域内的 `<em>` 元素包含文本
  `"This paper has been accepted for publication"`
- 不包含 `citation_pdf_url` meta 标签
- 有关 title/doi/authors/journal/online_date 的正常 meta 标签

**处理策略**：在 `OpticaScraper.parse_page()` 开头检测上述特征，立即抛出 `AcceptedPaperError`，
与 APS 统一由 Phase C 的 `AcceptedPaperError` 捕获逻辑处理。

**Phase C 行为**（与 APS 一致）：
1. `OpticaScraper.parse_page()` 检测到 Accepted Paper 特征 → 抛出 `AcceptedPaperError`
2. 捕获后从 `papers` 表删除（`db.delete_paper()`）
3. **不**记入 `skipped_dois`（同 DOI 正式版会在未来出现，Phase A 应能重新发现）
4. 后续阶段自然跳过

## 10. Session 缓存自动清理

**背景**：每个 publisher 使用独立的 Chromium profile 目录（`data/session_cached/<publisher>/`），
cloakbrowser 的 `launch_persistent_context()` 在其中存储 cookies、localStorage、浏览器缓存等。
若不清理，单个 publisher 的 profile 可达数百 MB，长期积累会占用大量磁盘空间。

**策略**：`BasePublisherScraper.close()` 在关闭浏览器上下文后自动执行 `shutil.rmtree()` 清理
profile 目录。清理在每次 Phase C 的 `finally` 块中执行（`pipeline/phase_c.py`），
确保无论抓取成功或失败，session 数据都会被移除。

**Session 目录仅存活于一次 Phase C 运行期间**——每次重新运行都会重新创建干净的 profile。

## 11. 抓取错误诊断：HTML 快照保存

**背景**：当 Phase C 抓取失败时，仅凭错误消息难以区分根因（Cloudflare 拦截、页面结构变更、
网络超时、APS 302 导航中断）。`fetch_page()` 的异常分支会保存页面 HTML 快照到
`data/raw/page/error/` 目录。

**文件命名格式**：`error_{doi}_{timestamp}.html`
- `doi`：失败的论文 DOI（特殊字符替换为 `_`，截断至 60 字符）
- `timestamp`：精确到秒的时间戳（`YYYYMMDD_HHMMSS`）

**触发条件**：
1. `fetch_page()` 中首次 `goto()` 异常后的重试再次失败
2. Cloudflare 拦截确认后（通过 CF 关键词检测）
3. `parse_page()` 抛出 `PageParseError`

**错误汇总日志**（`pipeline/phase_c.py` 失败出口）：
- 错误类型（`error_type`）
- 页面标题片段（从 HTML `<title>` 提取，前 120 字符）
- HTML 快照文件路径（`HTML saved to error dir`）

## 12. CLI/WebUI 配置隔离（journal_overrides 加载控制）

**背景**：Data Sources 页面对期刊启停的修改保存到 `data/journal_overrides.json`。
但这个文件被 Phase A 无条件加载，导致 CLI 运行时也受 WebUI 设置影响，与「CLI 和 WebUI 互不干扰」的设计原则冲突。

**策略**（`src/pipeline/phase_a.py`）：
- `phase_a_rss()` 和 `phase_a_crossref()` 增加 `use_overrides` 参数
- CLI（`runner.py` 中 `force=False`）→ `use_overrides=False` → 不加载 overrides，只读 `publishers.yaml`
- WebUI Pipeline 页（`force=True`）→ `use_overrides=True` → 加载 overrides 叠加到 publishers.yaml

**实现**：`runner.py` 中 Phase A-RSS 和 A-CR 的 args 传入 `force`：
```python
"A-RSS": (phase_a_rss, [db, publishers, force], ...),
"A-CR": (phase_a_crossref, [db, publishers, force], ...),
```

**`_journal_effective()` 修复**：`rss_enabled` / `cr_enabled` 查询时，在 overrides 中找不到时，
回退到 `journal.get("enabled", True)`（publishers.yaml 自身的 `enabled` 字段）。

## 13. Phase C Publisher 启停检查（enabled_publishers）

**背景**：`enabled: false` 在 publishers.yaml 中只阻止 Phase A 新增论文，
但数据库中已有的论文不受影响——Phase C 不检查 `enabled` 状态，状态为 `pending` 就处理。
这导致禁用 publisher 的旧论文仍会被浏览器抓取，浪费时间和 IP 信誉。

**策略**（`src/pipeline/phase_c.py`）：
1. `phase_c_publisher()` 签名增加 `publishers` 参数
2. 入口处构建 `enabled_publishers` 集合：只要有任一期刊 `enabled: true`，该 publisher 就视为启用
3. 遇到禁用 publisher 的 pending 论文 → 标记 `publisher_page_fetched_status = 'skipped'`，
   error 写入 `"Publisher disabled in publishers.yaml"`
4. 下游阶段自然跳过（上游已 skipped）

## 14. AIP PDF 下载三级回退链

> **2026-08-01 更新**：本节为历史决策记录。文中所述的 JS fetch 兜底已在 2026-08-01
> 重构中删除（全日志验证从未触发/触发即失败），当前实现见上文「下载优先级（2026-08-01 重构，
> 三级兜底链）」。本节保留以供回溯。

**背景**：AIP 的 PDF URL 是直接下载链接（`wget` 可直接下载），但浏览器 JS `fetch()` 被 CSP 拦截。
此处记录两条最终被弃用的尝试方案。

**主路径：JS fetch**（覆盖 6/7 publisher）：
```
page.evaluate(fetch(pdf_url))
```
Nature、Science、APS（DOM 扫描后）、Cambridge、IOP 均正常工作。

**v1 回退尝试（已弃用）：`page.goto(pdf_url) + response.body()`**
- 思路：浏览器原生导航不受 CSP 限制
- 失败：浏览器 PDF viewer 以 stream 消费响应体，`response.body()` 返回 None
- 本质：Playwright 对 PDF URL 的 `response.body()` 不可靠——不等 body 缓冲就消费了

**v2 回退尝试（已弃用）：`<a click> + page.expect_download()`**
- 思路：程序化创建 `<a download>` 并 `click()`，模拟用户点击触发浏览器下载
- 失败：AIP 不认 `element.click()` 为「用户手势」，不触发下载事件，60s 超时
- 本质：JS 合成事件（`event.isTrusted=false`）不等于真实用户交互，部分网站据此过滤

**当前主路径：`requests` + 浏览器 cookies + User-Agent**（2026-06-07 优化）：
```python
cookies = self.context.cookies()
session = requests.Session()
for c in cookies:
    session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
try:
    ua = self.page.evaluate("navigator.userAgent")
except Exception:
    ua = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
session.headers.update({"User-Agent": ua, "Referer": page_url})
resp = session.get(pdf_url, timeout=120)
pdf_body = resp.content
```
- AIP 的安全模型是「浏览器 JS 层 CSP + 用户手势检测」，PDF URL 在 HTTP 层无校验
- 纯 HTTP 请求绕过 CSP、用户手势、TLS 指纹等所有浏览器层防御
- 提取的 cookies 携带浏览器 session，User-Agent 和 Referer 使请求在 HTTP 层与浏览器导航无异
- **2026-06-07 改为第一顺序**：原先 JS fetch 主路径在 AIP 上需等 60s 超时才降级，
  反转后 requests 秒级失败，JS fetch 降为兜底。同时 `navigator.userAgent` 获取加 try/except 保护，
  防止导航销毁上下文导致崩溃。

## 15. LLM 相关性四级分类体系（A/B/C/D）

### 背景

旧版 Phase E 使用二分类（relevant=1/0），存在两个问题：
1. **粒度过粗**：一篇关于激光尾场加速的纯模拟论文、一篇涉及等离子体聚焦技术的方法论文、一篇天文等离子体的文章，在旧体系下分别被标注为 1、1、0，但前两者在质上完全不同。
2. **Prompt 与领域描述耦合**：`domain_description` 是单一文本段，无法直接包含"不相关领域"的负例边界，导致误判率偏高。

### 四级分类定义

| 类别 | 标签 | 含义 | 后续处理 |
|------|------|------|---------|
| **A** | 直接相关 | 有激光驱动离子/质子、激光靶与直接诊断、后加速、激光驱动紧凑束线、束流辐照效应与明确下游应用，或等离子体波导/通道形成、演化、稳定性与表征的正向证据；纯电子 LWFA 作为波导应用不改变 A | → E2/E3 候选 |
| **B** | 间接相关 | 论文实际展示了可不改变核心原理而迁移的具体技术、器件、算法或诊断方法；ICF/低温靶送靶仅在实际展示高重复频率激光聚焦条件下可迁移的输运/注入时为 B，非激光聚变/Z-pinch/DPF 中实际展示的 FLASH/MHD、鞘层跟踪或合成诊断也可为 B | → E2/E3 候选 |
| **C** | 同领域但远 | 同属加速器/等离子体领域，但与核心兴趣距离较远 | → E2/E3 候选 |
| **D** | 基本无关 | 不属于课题组关注范围 | 仅低置信 D → E2/E3；高/中置信 D 终止 |

Phase E 的分类是高召回初筛，不直接决定报告资格。E2/E3 覆盖 A/B/C 与低置信 D，E3 用正文作最终分类；只有终审 **A 或 B**、且 `llm_relevance_basis='fulltext'`、并完成 Phase F 总结的论文才进入 G/H。正文暂不可用时最终相关性保持 `pending`，由 daily 自动重试 MinerU；用户手动导入 PDF 后继续 E2→E3，不以标题/摘要降级入报。

### 匹配子领域记录

LLM 同时输出 `MatchedSubfields`（JSON 数组），记录论文命中了 `scope_definition` 中哪些子领域。此信息存储在 `llm_relevance_subfields` 列，供 WebUI Papers 页展示和后续分析。

### 子领域 Key 规范化（2026-06-16）

LLM 输出中的子领域 key 存在约 5% 的格式偏差（大小写不一、空格/下划线混用、含标点）。
`phase_e.py` 加入 post-processing：
1. 小写化 + 空格→下划线
2. 去除首尾标点（`. , ; : ! ?`）
3. 与 `scope_definition` 已知 key 列表校验
4. 未知 key 保留原值并记录 debug 日志

### Prompt 策略

Prompt 使用 `configs/keywords.yaml` 中的 `context_gates`（Step 1 词义消歧）、`irrelevant_fields`（Step 2 主题黑名单）、`scope_definition`（Step 3 正类子域）三段，由 `config.build_scope_block()` 按 Step 1 → Step 2 → Step 3 顺序渲染为带 `# Step N: ...` 前缀的分节文本块，嵌入 `configs/prompts/relevance.yaml` 模板。

LLM 被要求按**决策树**顺序执行：

| 步骤 | 操作 | 终止条件 |
|------|------|---------|
| (a) | 应用 context_gates 做 per-term 消歧 | out-of-scope 标记的 term **不得**进入 sub-domain 匹配 |
| (b) | 论文主话题是否匹配 irrelevant_fields | **YES → D + MatchedSubfields 空 + 停止** |
| (c) | 分配 A/B/C/D（基于 scope_definition） | A=直接研究子域；B=方法/技术可迁移；C=同领域但距离远；D=不在研究领域（Step 2 没拦住的残差） |
| (d) | 若 A/B 列 sub-domain key（最多 2 个） | 无明确匹配时 MatchedSubfields 留空 |

A/B/C/D 的权威定义在 `configs/prompts/relevance.yaml` 决策树 (c) 步内，**报告头部图例**（`_relevance_legend_md`/`_relevance_legend_html`）从同一来源转写以保持一致。

### 旧版到新版的迁移

| 维度 | 旧版 | 新版 |
|------|------|------|
| 存储列 | `llm_relevance_result INTEGER (0/1)` | `llm_relevance_category TEXT (A/B/C/D)` + `llm_relevance_subfields TEXT` |
| 旧列状态 | 主列 | **废弃**，不再写入，择机删除 |
| 过滤条件 | `llm_relevance_result = 1` | `llm_relevance_category IN ('A', 'B')` |
| Prompt 数据类型 | `domain_description`（单段中文） | `scope_definition`（6 子域）+ `irrelevant_fields` |
| LLM 输出 | `{relevant, confidence, reason}` | `{PredictedCategory, MatchedSubfields, Confidence, Notes}` |
| 关键词匹配源 | `keywords` 列表 | 从 `scope_definition[].topics` 自动抽取 |

## 16. Accepted Paper 生命周期管理（删除策略）

APS Accepted Paper 是正式发表前的预发布版本，URL 含 `/accepted/`，
页面结构不同于正式论文（无 PDF、无完整摘要选择器）。这些论文后续
会以正式论文形式（**同 DOI**）发表，因此数据库中的预发布记录必须
被**删除**，而非标记跳过。

### 问题根因

旧方案将 Accepted Paper 标记为 `skipped` 并 cascade skip 下游阶段，
但数据库的 `doi UNIQUE` 约束使得正式版发表后流水线无法重新发现和
处理该论文——`paper_doi_exists()` 返回 True 阻止了一切。

### 检测策略（`APSScraper.parse_page()`）

| 方法 | 检测依据 |
|------|---------|
| 精确检测 | URL 路径含 `/accepted/` |
| 特征标签 | `li.article-feature-tag` 内容为 `Accepted Paper` |

### 触发后的行为

`AcceptedPaperError` 被捕获后，`phase_c.py` 执行：
1. `db.delete_paper(doi)` — 直接从数据库删除整条记录
2. 下一篇 Phase A-CR 运行时，正式论文将被重新发现并正常处理

### 处理策略对比

| 类型 | 处理方式 | 原因 |
|------|---------|------|
| **Accepted Paper** | **删除** | 同 DOI 正式版会在未来出现 |
| **Erratum / Comment 等** | **删除** | 永远不会变成研究论文（下次 RSS/CrossRef 发现时重新检查，此时若已附带原文链接则正常入库） |
| **正常空摘要论文** | **正常处理**（标注 success） | 有标题+DOI，无特殊标记 |

## 17. Logging 配置三入口模型

Logger 配置从 `pipeline/base.py` 移到各入口点（entry point），每个入口点独立拥有自己的
logging 配置，不再在模块 import 时被动初始化。

### 入口点

| 文件 | 入口函数 | 用途 | Logger 配置 |
|------|---------|------|------------|
| `src/main.py` | `run_pipeline()` | CLI 全流程 (A→H) | `RotatingFileHandler` + `StreamHandler` |
| `tools/schedule_daily.py` | `run_daily()` | Cron 每日 (A→F) | `RotatingFileHandler` + `StreamHandler` |
| `tools/schedule_weekly.py` | `run_weekly()` | Cron 每周 (G→H) | `RotatingFileHandler` + `StreamHandler` |

### 日志轮转

统一使用 `RotatingFileHandler`：
- 单文件上限：10MB
- 备份数：5（保留最近 5 个轮转文件）
- 编码：UTF-8

### LOG_LEVEL 环境变量

所有入口点支持 `LOG_LEVEL` 环境变量（默认 `DEBUG`）：
```bash
LOG_LEVEL=INFO python src/main.py
```

### 自动重置（schedule_daily.py 入口）

`tools/schedule_daily.py` 在调用 `run_daily()` 前自动重置失败状态为 `pending`：
- `publisher_page_fetched_status = 'failed'`（Cloudflare 瞬态拦截等偶发失败）
- `mineru_parse_status IN ('failed', 'skipped')`
- `llm_relevance_status = 'failed'`（如 LLM API 临时降级导致的判断失败）

使偶发失败的论文在每次每日运行时自动获得重试机会。
仅重置 `failed` 状态，不触碰 `skipped`（`skipped` 通常表示合法的非论文/无摘要条目）。
`tools/run_pipeline.py` 使用同一逻辑，可通过 `--no-reset-*` 逐项关闭。

## 18. 配置持有对象（CFG）

**背景**：`config.py` 使用模块级裸变量（`SKIP_PHASE_A_RSS = False`）持有运行时配置。
`reload_config()` 用 `global` 修改它们。其他模块通过 `from config import X` 获取值副本。
Web UI 长进程中 `reload_config()` 更新了 `config` 模块的变量，但 `web/app.py` 的
`PHASE_DEFAULTS` dict 在 import 时捕获的值不会自动跟随。这是 Python 值复制 + 模块级可变
状态的经典陷阱。

**解决**：引入 `CFG` 持有对象（`types.SimpleNamespace`），所有可热加载的运行时配置作为其属性。

### 设计

```
# config.py
from types import SimpleNamespace
CFG = SimpleNamespace()
CFG.SKIP_PHASE_A_RSS = False

def reload_config():
    CFG.SKIP_PHASE_A_RSS = new_value  # 不需要 global

# 任何消费者
from config import CFG
if CFG.SKIP_PHASE_A_RSS:   # 属性访问 → 永远实时 ✅
```

**关键差异**：
- `from config import X` → **值复制**，过期
- `from config import CFG; CFG.X` → **属性访问**，永远当前值

### `_apply_settings()` 去重

引入 `_apply_settings(settings)` 函数，被模块加载和 `reload_config()` 共同调用，
消除原先 ~80 行重复代码：

```python
_SOURCE_SETTINGS = load_settings()
if _SOURCE_SETTINGS:
    _apply_settings(_SOURCE_SETTINGS)

def reload_config():
    _settings = load_settings()
    if _settings:
        _apply_settings(_settings)
```

### 消费者迁移

| 文件类别 | import 方式 | 说明 |
|---------|------------|------|
| `web/app.py`（长进程） | `from config import CFG; CFG.X` | 热加载实时生效 |
| `pipeline/*.py`（子进程） | `from config import CFG; CFG.X` | 统一风格，子进程重新 import 时拿到当前值 |
| `config.py` 自身 | `CFG.X = ...` | 属性写入 |

### 不变部分

路径常量（`DATA_DIR`、`DB_PATH`、`RAW_RSS_DIR` 等）、.env 密钥（虽然在 `CFG` 上有别名但永不热加载）、加载函数（`load_publishers()`、`load_keywords()` 等）保持模块级变量/函数不变。

## 19. CrossRef 摘要驱动 Phase C 跳过

**背景**：Optica / Optics Express 是 Open Access 期刊，CrossRef API 返回完整的元数据和摘要。
Phase C 浏览器访问仅用于提取 `pdf_url` 和少数缺失字段，但每次启动浏览器耗时 30-60s 且消耗反爬额度。

**策略**：Scraper 类增加 `skip_phase_c_if_crossref_abstract` 类属性，Phase C 在启动浏览器前检查：
```
if scraper_class.skip_phase_c_if_crossref_abstract:
    for paper in papers:
        if DB 中 cr_metadata_fetched_status = 'success' AND abstract 非空:
            标记 publisher_page_fetched_status = 'skipped'
            不进入浏览器访问
    √ 剩余论文正常走浏览器路径
```

**收益**：
1. 节省 Optica 反爬额度（将有限浏览器预算留给真正需要提取正文的论文）
2. 加速 Pipeline（跳过浏览器启动和页面加载，每篇节省 ~30-60s）
3. 降低 CF 拦截风险（减少浏览器指纹总流量）

**PDF URL 延迟补齐（Phase E2）**：跳过 Phase C 的 Optica 论文缺少 `pdf_url`。
`phase_e2_mineru()` 对 `publisher == "optica"` 且 `pdf_url` 为空的论文仍执行延迟页面访问，
使用 `OpticaScraper` 提取 `pdf_url` 后调用 `db.update_publisher_pdf_url()` 仅更新 `pdf_url` 字段，
不覆写 Phase C 状态。

# 流水线子阶段详解

## Phase C — Publisher 页面抓取

> **代码结构（2026-08-01 重构）**：`sources/publisher.py` 中 `BasePublisherScraper` 提供
> 6 个共享静态 helper——`_extract_meta(sel, name)`、`_extract_meta_all(sel, name)`、
> `_extract_attr(sel, css_selector)`、`_extract_canonical_url(sel)`、`_join_texts(parts)`、
> `_clean_abstract_text(text)`。7 个出版社子类的 `parse_page()` 统一用这些 helper 提取
> `citation_*` meta 与摘要文本，消除重复；各出版社仅保留差异点（date meta 名
> publish_date/citation_date/citation_online_date、摘要 XPath、类型过滤逻辑）。

使用 cloakbrowser 驱动 headful Chromium 和持久化 browser context：
- 同一 publisher 共用一个 session（`data/session_cached/<publisher>/`）
- cloakbrowser 自动处理浏览器指纹伪装，无需手动注入反检测 JS
- 页面间随机延迟 `PUBLISHER_PAGE_DELAY_MIN~MAX`（默认 3-5s），publisher 间冷却 15s
- 失败熔断：连续失败 `PUBLISHER_MAX_CONSECUTIVE_FAILURES`（默认 3）篇后自动中止，避免 IP 封禁
- **Publisher 启停检查**：运行前从 `publishers.yaml` 构建 `enabled_publishers` 集合，
  禁用 publisher 的 pending 论文直接标记 `skipped`，不浪费浏览器启动时间（详见「韧性策略 #12」）
- **Prewarm 预热**（`BasePublisherScraper.prewarm_url`，2026-08-09）：某些站点（如 AIP 的 Osano 同意墙）在
  浏览器冷启动后首次访问论文页只返回 head-only 空壳（无 body / 无 `citation_*` meta），需先访问域名根建立
  同意/Cookie 态。Phase C 在抓取每个 publisher 前调用 `scraper.prewarm()`（无 `prewarm_url` 则 no-op）：
  先 `goto` 域名根（domcontentloaded）→ 等 15s → 若仍是 CF challenge 再等 15s；异常仅记 warning，不影响主流程。
  目前仅 `AIPScraper` 设置 `prewarm_url = "https://pubs.aip.org"`。背景：AIP 唯一每日失败的论文
  `10.1063/5.0339025` 因 `get_pending_publisher_papers` 无 ORDER BY（最早 rowid 恒为该组第一篇）且
  `retry_attempts=[2]` 只给单次 45s 尝试，冷启动首次访问恒拿到同意墙空壳页（详见 tasks.md 2026-08-09）
- **CrossRef 摘要驱动跳过**：对于设置了 `skip_phase_c_if_crossref_abstract=True` 的 Scraper 类（如 Optica），
  Phase C 在浏览器启动前检查 DB 中已有 CrossRef 摘要的论文，直接标记 `skipped` 跳过浏览器访问。
  此优化节省反爬额度并加速 Pipeline（详见「关键设计决策 #15」）
- **Pre-fetch 非研究论文检测**（`configs/settings.yaml` 配置）：在浏览器启动之前根据 DB 中的论文标题进行前缀匹配（`startswith`），匹配到 `erratum`、`author correction:`、`publisher correction:`、`comment on`、`response to`、`publisher's note` 等关键词时直接 `delete_paper()` + `insert_skipped_doi()`，避免浏览器启动和重试消耗。pre-fetch（`prefetch_non_research`）和 post-fetch（`postfetch_non_research`）有独立开关，关键词列表（`non_research_keywords`）由用户配置
 - **Bot 拦截检测**（parse_page 之后）：仅当 `parse_page()` 返回空结果（title+doi+abstract 全空）时才检查 bot 标记；
   检测范围包括：
   - Cloudflare: `challenge-platform`、`_cf_chl_opt`、`cf-browser-verification`、`cf-ray` + 短 HTML、`turnstile` + `challenge`
   - Radware Bot Manager: `radware`、`bot manager`（HTML 和页面标题）
   - Captcha 页面标题: `captcha`
   - Nature Client Challenge (JS 验证): `javascript is disabled`（HTML 内容）、`client challenge`（页面标题）
   - 异常处理中也增加 bot 检测（含页面标题提取），bot 拦截导致的异常走完整重试而非 attempt 0 终止
 - **Cloudflare challenge reload 恢复**（`fetch_page` 内，2026-08-01）：AIP/APS 在快速连续请求下会触发 Cloudflare
   Turnstile **managed challenge**（页面标题「请稍候…」，正文「验证成功。正在等待响应」）。实测确认 challenge 页加载时
   `cf_clearance` cookie 已写入持久化 context，但页面本身卡在验证结果等待中——此时 `page.reload()` 用该 cookie
   直接放行拿到真实文章页。旧逻辑每次 retry 只重新 `goto` 同一 URL，会一直卡在 challenge。新增：
   - `_is_cf_challenge_page()`：只检查挑战页特有结构标记（`cf-chl-widget` / `_cf_chl_opt` / `challenge-error-text` /
     正文「正在进行安全验证」「验证成功」/ 标题「请稍候」「just a moment」「attention required」），
     **不**匹配真实文章页也内嵌的 `cf-turnstile` / `challenge-platform` CDN 脚本，避免误判。
    - `fetch_page()` 在初始等待后若检测到 challenge，循环 reload（`PUBLISHER_CHALLENGE_MAX_RELOADS`，默认 2 次），
      每次 reload 后**轮询**等待页面放行（每 10s 检查一次 `_is_cf_challenge_page`，页面提前放行则提前退出，
      最坏等到 `PUBLISHER_CHALLENGE_RELOAD_WAIT_MS`（默认 45s）截止）再重新取 HTML。
   - `start_browser()` 启用 `humanize=True`（人类鼠标/键盘/滚动行为模拟），提升行为指纹得分，降低 challenge 触发概率。
   - 配置项：`publisher.challenge_max_reloads` / `challenge_reload_wait_ms`（`configs/settings.yaml`）。
   此机制对所有 publisher 生效（reload 仅在检测到 challenge 时触发，正常页面零开销）。
- 按 publisher 分组处理，同一组复用浏览器实例（`SCRAPER_MAP` 管理 7 个 publisher）
- Session 缓存自动清理：`BasePublisherScraper.close()` 在每次 publisher 组处理完毕后
  执行 `shutil.rmtree()` 清理 Chromium profile 目录（详见「韧性策略 #9」）
- 错误诊断：`fetch_page()` 异常时自动保存 HTML 快照到 `data/raw/page/error/`
  （详见「韧性策略 #10」）

7 个 Scraper 子类各适配不同的页面结构（meta 标签 / JSON-LD / XPath）。

### HTTP 回退（Nature + IOP）

对 Cloudflare / Fastly 浏览器拦截概率高的 publisher，增加纯 HTTP 回退路径替代浏览器渲染：

| Publisher | 模式 | 策略 | 需求 |
|-----------|------|------|------|
| Nature (nature.com) | `requests` | `primary`（浏览器前） | 内置 requests 库 |
| IOP (ioppublishing.org) | `curl_cffi` | `fallback`（浏览器后） | 需安装 `curl-cffi` |

**`_is_bot_page()` 检测**：通过标题和 HTML 关键词匹配识别 Cloudflare、Fastly、Radware、reCAPTCHA、Nature Client Challenge 等 bot 拦截页面。若浏览器渲染后仍被拦截，则尝试 HTTP 回退。

**反检测 JS 注入**：`start_browser()` 使用 `page.context.add_init_script()` 注入 `navigator.webdriver` 覆盖、`navigator.plugins` 填充等反检测脚本，在每次页面导航前自动执行。

**回退链**：
```
Nature (primary): 浏览器 goto → bot 拦截 → _is_bot_page? → HTTP requests → 成功则用 HTTP HTML
IOP (fallback):   浏览器 goto → bot 拦截 → _is_bot_page? → curl_cffi → 成功则用 curl HTML
                  浏览器 goto → 成功 → 正常使用浏览器 HTML
```

### Optica CrossRef 驱动跳过

Optica / Optics Express 为 Open Access 期刊，CrossRef 返回完整元数据和摘要。
对于已从 CrossRef 获得 abstract 的 Optica 论文，Phase C 自动跳过浏览器访问，
将 `publisher_page_fetched_status` 标记为 `skipped`（实现于 `phase_c.py` 的 publisher 循环头部）。

此优化带来三重收益：
1. **节省 Optica 反爬额度** — 将有限的浏览器访问预算留给真正需要提取正文的论文
2. **加速 Pipeline** — 跳过浏览器启动和页面加载（每篇节省 ~30-60s）
3. **降低拦截风险** — 减少浏览器指纹流量，降低触发 CF 拦截的概率

### Optica 反爬注意事项

Optica 浏览器访问仍保留以下反爬注意项（仅对 Phase C 未跳过的论文生效，
即在 CrossRef 中找不到 abstract 的论文仍需浏览器访问）：

| 因素 | 详情 |
|------|------|
| IP 敏感度 | Optica Publishing Group 对非美国出口 IP 极敏感，必须配置美国代理 |
| 代理配置 | `config.py` 中 `PUBLISHER_PROXY = {"optica": {"server": "http://127.0.0.1:10808"}}` |
| 请求频率 | 默认 3-5s 页面间隔低于 Optica 反爬阈值，成功篇数越多越容易触发拦截 |
| Session 共享 | Optica 和 Optics Express 共用 `publisher: optica` → 同一 browser session + 同一熔断计数器，一个被拦两者皆受影响 |
| 拦截模式 | 成功爬取一定篇数后触发 CF 拦截，成功率随连续成功数递减，最终完全阻断 |

已知缓解方向（未实现，按需选用）：
- **独立延迟**：新增 `OPTICA_PAGE_DELAY_MIN/MAX`，Optica 使用更宽松延迟（建议 10-20s）
- **成功冷却**：每成功 N 篇后强制冷却 60s，在拦截发生前主动降温
- **Session 分离**：opex 使用独立 `publisher` 标识 + 独立 Scraper 子类，隔离熔断
- **代理 IP 轮换**：多路代理轮流使用，降低单 IP 请求密度

## Phase E2 — PDF 下载策略

`BasePublisherScraper.download_pdf()` 处理 PDF 下载，使用 requests+cookie 先行的双路径策略。

### 建立上下文

1. `goto(page_url)` 访问文章页，等待 15s 充分稳定（APS 302 二次导航需要更长时间）
2. 扫描 DOM 中 `<a>PDF</a>` 提取同域 URL（解决 APS 跨域问题）
   - 二次导航可能销毁执行上下文 → try/except + 3s 重试
   - 提取失败时保留原始 `pdf_url`（跨域链接），后续下载路径仍可用
3. 下载后**立即保存**到 `data/mineru_output/<safe_doi>/paper.pdf`（不再用 tempfile），保存前校验 `%PDF-` 头部

### 下载优先级（2026-08-01 重构，三级兜底链）

```
[on_page_url 同域改写]（仅 APS 启用）
   └── requests + 浏览器 cookies (第一优先级, 秒级失败)
         └── 失败 → context.request.get() (第二优先级, 继承代理/cookie)
                └── 失败 → 浏览器导航下载 (第三优先级, goto + expect_download)
```

**前置（仅 APS 启用）：on_page_url 同域改写**
- APS 的 `citation_pdf_url` 是 `link.aps.org` 跨域重定向链接，需从文章页提取同域
  `journals.aps.org` 直链后用 requests 下载（2026-06-01 为修复 APS 跨域失败加入）。
- 通过类属性 `extract_on_page_pdf_link` 门控，**仅 APSScraper 开启**：
  其他 publisher 关闭，避免误选文章页中的配图下载链接（Optica 曾 2 次误选
  `viewmedia.cfm?uri=...&figure=...&imagetype=pdf`）。

**第一优先级：requests + 浏览器 cookies**
- 从浏览器 context 提取登录态 cookies + User-Agent，用 Python requests 做 HTTP 直连下载。
- **全日志验证为唯一真正有效路径**：169 次下载尝试中绝大多数成功都靠它，
  复用浏览器 context 的 `cf_clearance` 等反爬 cookie，对所有 publisher 通用。
- 不受 CSP 限制（AIP 的 `connect-src` 拦截 JS `fetch()`，但不拦 requests）。

**第二优先级：context.request.get()**（2026-08-01 新增）
- 使用 Playwright `APIRequestContext.get(pdf_url, headers={Referer})`，继承浏览器
  上下文的代理和 cookies，但**不做真实页面导航**。
- 专为 Optica 设计：Radware 拦截经代理放行后返回完整 PDF，而 Chrome 内置 PDF viewer
  **内联渲染** signed `directpdfaccess/*.pdf` URL，不触发 download 事件——
  `expect_download()` 永远等不到。实测 `context.request.get()` 在代理下对
  `viewmedia.cfm` 和 signed URL 均直接返回完整 PDF（200, `application/pdf`）。

**第三优先级：浏览器导航下载**（保留为最后兜底）
- 使用 `page.goto(pdf_url) + page.expect_download()` 模拟用户点击 "Get PDF" 按钮。
- 全日志验证从未成功过（Chrome 内联渲染 PDF 无 download 事件），保留仅作理论兜底，
  **不是 Optica 的解法**。

### PDF 复用

`phase_e2.py` 支持已下载 PDF 的本地复用，避免重复下载：

1. 进入处理前检查 `data/mineru_output/<safe_doi>/paper.pdf` 是否存在
2. 存在 → 读取前 5 字节校验 `%PDF-` 头部 + 非空检查
3. 校验通过 → 跳过下载，直接传入 `parser.parse_pdf()` 开始 MinerU 解析
4. 校验失败（文件损坏/非 PDF）→ 删除后重新下载覆盖

此设计与「PDF 立即保存」配合生效：MinerU 上传失败后重跑 Phase E2 时，已保存的 PDF 直接复用，不重复下载。

### 手动 PDF 导入（2026-07-20）

针对部分论文在 Phase E2 反复下载失败的场景，新增 `tools/import_local_pdf.py`：用户自行下载 PDF 后导入，下次调度命中上述「PDF 复用」逻辑跳过下载。

```
python tools/import_local_pdf.py --doi <DOI> --pdf <PATH_TO_PDF>
```

流程：
1. 校验源文件存在 + `%PDF-` 头部
2. 计算 `safe_doi`（规则与 `phase_e2.py:149` 一致）→ 复制到 `MINERU_OUTPUT_DIR/<safe_doi>/paper.pdf`
3. UPDATE 该 DOI 的 `mineru_parse_status='pending'`、`mineru_parse_error=NULL`、`mineru_parse_date=NULL`（不动 `pdf_url`/`mineru_output_dir`/`doi`）
4. 下次 daily 调度跑 Phase E2 时命中复用逻辑，直接交给 MinerU

退出码：1=文件不存在/异常，2=非 PDF 头部，3=DB 无该 DOI 记录（PDF 已落盘，需先跑 Phase A-E 让论文入库）。

设计取舍：方案 A（独立脚本，不改 pipeline）+ 单篇模式 + 只重置状态不自动续跑——风险最低，完全复用现有复用逻辑，不引入新代码路径。

### Optica 延迟页面访问（Phase E2）

Optica OA 论文因 Phase C 被跳过（`publisher_page_fetched_status = 'skipped'`），
`pdf_url` 字段为空。Phase E2 在 PDF 下载前先执行延迟页面访问补齐 `pdf_url`：

1. 筛选 Optica 的初筛候选论文时，允许 `pdf_url` 为空（`publisher == "optica"` 特例）
2. 浏览器启动后（使用 `OpticaScraper` 而非 `BasePublisherScraper`，以获取 `parse_page()` 能力），
   对每组中缺少 `pdf_url` 的论文执行 `fetch_page(page_url) + parse_page()`
3. 成功提取 `citation_pdf_url` meta 标签后，通过 `update_publisher_pdf_url()` 写入数据库
   （只更新 `pdf_url` 列，不影响 Phase C 的 `skipped` 状态）
4. 若页面解析也未返回 `pdf_url`，论文被标记 `mineru_parse_status = 'failed'` 并跳过

### APS 导航容错

APS 使用 `link.aps.org` → `journals.aps.org` 双域名架构，goto 后的二次导航可能
在任何时刻销毁执行上下文。`download_pdf()` 包含三层防护：

| 层 | 防护 | 失效时 |
|----|------|--------|
| 1 | `wait_for_timeout(15000)` 等待充分稳定 | 进入第 2 层 |
| 2 | `for _attempt in range(2)` + except 重试 | 保留原始 `pdf_url`（跨域） |
| 3 | 主路径 requests+cookie 全局兜底（第 2 层非必需——即使没提取到同域链接，requests 也可用原始 URL） | context.request / 导航下载兜底 |

### 已弃用的尝试（记录教训）

- `page.goto(pdf_url) + response.body()` — 浏览器 PDF viewer 以 stream 消费响应体，
  `response.body()` 返回 None（不等缓冲就消费了）
- `<a click> + page.expect_download()` — 程序化 `element.click()` 不被视为"用户手势"，
  `event.isTrusted=false`，不触发下载事件（用于 AIP，AIP 检测 JS 合成事件）
- **当前第三级兜底 `goto(pdf_url) + expect_download()` 与上述尝试不同**：
  - 不依赖 `element.click()`（不触发 isTrusted 检测）
  - 不依赖 `response.body()`（不关心 PDF viewer 行为）
  - 直接导航到 PDF URL 触发浏览器原生下载事件
  - 此方法在 AIP 上可能同样有效，但 AIP 的 requests+cookie 路径已足够快

### Optica PDF 下载实测结论（2026-08-01）

针对 Optica 长期失败（`mineru_parse_status='failed'`，Radware Bot Manager captcha）
做了 8 组浏览器矩阵（直连/humanize/代理 7890 × 2 篇论文），结论：

| 配置 | 结果 |
|------|------|
| 直连（含 humanize） | 被 Radware 拦，跳转 `opg.optica.org/captcha/(S(...))/?guid=...` 标题 Captcha |
| 代理 7890（含 humanize） | Radware 放行，`viewmedia.cfm` 302 → `directpdfaccess/{uuid}_{id}/...pdf?da=1&id=...&seq=0`（signed URL） |

- **humanize 无法通过 Optica 的 Radware captcha**——根因是 IP 信誉（直连 222.29.111.129），
  代理出口（116.251.216.10）才放行。
- **代理下第二三级路径仍会失败**：Optica 用 signed `directpdfaccess/*.pdf` URL，
  Chrome 内置 PDF viewer **内联渲染**，不触发 download 事件 → `expect_download()` 超时。
- **关键突破**：`context.request.get(pdf_url)`（Playwright APIRequestContext，继承
  浏览器代理/cookie）在代理下对 `viewmedia.cfm` 和 signed URL **都能直接返回完整 PDF**（200, `application/pdf`）。
- **已实施修复（2026-08-01）**：`download_pdf()` 兜底链重构为
  `on_page_url（仅 APS）→ requests+cookies → context.request.get() → goto+expect_download`，
  删除了全日志从未触发过的 JS fetch 死代码。E2E 实测 `OpticaScraper.download_pdf()`
  经代理 7890 成功抓取 oe604196 完整 PDF（7.8MB）。
- 另注：直连时 `context.request` 也会被 Radware 拦（返回 2320B HTML captcha），
  故代理配置是前提，不可省略。

## Phase F — LLM 结构化总结

- 仅处理 Phase E3 已完成正文终审（`llm_relevance_basis='fulltext'`）且为 A/B 的论文；没有全文时保持 pending，不生成摘要或报告
- MinerU 全文路径解析：`mineru_output_dir` 在 DB 中存储为相对于 `DATA_DIR` 的路径，Phase F 使用 `DATA_DIR / output_dir / "full.md"` 拼接（曾误用 `DATA_DIR.parent` 导致 `full.md` 找不到，所有论文被跳过）
- 使用 `ThreadPoolExecutor` 并发调用 DeepSeek API
- 输出 JSON 包含 5 个字段：`one_sentence`、`motivation_and_goal`、`key_setup_and_method`、`main_results_and_physics`、`take_home_message`
- 可选后处理：`FormulaFixer`（实验性，`SKIP_FORMULA_FIX = True` 默认关闭），用 flash 模型修复公式格式问题
  - 纯文本进/纯文本出：`json.loads` 后的 Python 字符串直接送 LLM，避免 JSON 转义带来的理解负担
  - 预检测：`needs_fix()` 先移除已正确包裹的 `\(...\)` / `\[...\]` 区域，剩余文本中如有 `\command` 残留才调 API
  - 逐字段修复 + `json.dumps()` 自动转义写回 DB
- **LLM 输出约束**：`SUMMARIES_PROMPT` 中明确禁止 LLM 使用复杂 LaTeX 环境（`\begin{}`/`\end{}`）和 `\\` 换行，仅允许基本命令和上下标。禁止原因详见「关键设计决策 #10」。

# PDF 转换路径

提供三种转换策略，按推荐优先级排列：

**KaTeX 路径（实验性）**：`src/processors/md_to_pdf_katex.py`
1. Markdown 嵌入含 KaTeX + marked.js 的 HTML 模板
2. cloakbrowser 加载 HTML，marked.js 渲染 Markdown → HTML
3. KaTeX 渲染 `\(...\)` / `\[...\]` 公式为排版数学
4. `page.pdf()` 输出 PDF
5. **支持 `\(`/`\[\]` 公式**，渲染结果与 WebUI 完全一致，不依赖 pandoc/texlive

> ⚠️ **已知问题**：标题前间距、分节渲染等细节尚不完善，输出效果可能与预期有差异。

```bash
python src/processors/md_to_pdf_katex.py data/reports/auto/report_YYYYMMDD.md
```

**传统路径**：`src/processors/pdf_converter.py` — pandoc + xelatex
- 策略 A：自定义 LaTeX 模板（含 `xeCJK`、`Noto Sans CJK SC`、`\times` 兼容宏）
- 策略 B：无模板回退（适用于纯英文场景）
- 返回 `None` 表示失败（不抛异常）

# reset 工具族

`tools/reset_pipeline.py` 提供 6 个子命令，每个支持 `--publisher` 过滤：

| 命令 | 重置范围 | 默认条件 | 级联 | 典型用途 |
|------|---------|---------|------|---------|
| `reset-relevance` | `llm_relevance_*`（及初筛快照列） | `failed`/`skipped`（`--all` 含 success）；`--categories` 按类别；`--dois` 精确 DOI | 无 | 修改 scope_definition 后；针对样例论文复核时用 `--dois` |
| `reset-publisher` | `publisher_page_fetched_status/error`（2 列） | `failed`/`skipped`（跳过 NonResearchPageError） | 无 | 重试被 CF 拦截的论文 |
| `reset-mineru` | `mineru_parse_*`（5 列） | `failed`/`skipped` | 无 | 重试 PDF 解析失败的论文 |
| `reset-summary` | `llm_summary_*`（4 列） | `failed`/`skipped`（`--all` 含 success） | 无 | 修改 prompt 后重生成总结 |
| `reset-report` | `report_status/date`（2 列） | `reported`（`--today`/`--days` 按日期） | 无 | 重新汇入下次报告 |

关键设计：
- `reset-relevance` **不级联** E2/F/G（相关性结果不影响已有 MinerU 全文和 LLM 总结）
- `reset-publisher` **跳过** `NonResearchPageError` 条目（非论文页面重试无意义）
- `reset-mineru` / `reset-summary` 重新解析/总结后，下游状态为 pending 的被自动拾取（无需显式级联）
- 所有命令执行前打印影响行数，交互确认后才执行
- `reset-relevance --dois DOI1,DOI2` 使用 `LOWER(TRIM(doi))` 精确匹配，不区分 DOI 大小写；与 `--all`、`--categories` 互斥，可继续叠加 `--publisher`

# Hugo 报告部署

## 工作流

`run_weekly.sh` 在 Phase G/H 之后自动将报告部署到 GitHub Pages：

```
run_weekly.sh
  ├── python tools/schedule_weekly.py          # Phase G + H
  └── python tools/convert_reports_to_hugo.py --all --hugo --deploy
                         ↓
  ├── site/content/reports/report_*.md          # 复制报告 + 加 front matter
  ├── hugo 构建 → site/public/                  # 生成 HTML
  └── ghp-import -p -f site/public/ → gh-pages  # 部署
```

`site/` 为本地 Hugo 基础设施（不提交到 git）。ghp-import 自动创建/更新 `gh-pages` 分支。

## 转换脚本

`tools/convert_reports_to_hugo.py` 支持：

| 参数 | 作用 |
|------|------|
| `--report <path>` | 指定报告文件 |
| `--all` | 转换全部 auto 报告 |
| `--hugo` | 转换后 `hugo` 构建 |
| `--deploy` | 构建后 `ghp-import` 部署 |
| `--dry-run` | 预览 |

说明：
- `--all` 只处理 `data/reports/auto/` 目录下的报告，排除 user 目录
- `--all` 会先清理 `site/content/posts/` 中 front matter `source: "auto"` 的文件再重新写入（按 `source` 字段过滤，避免误删用户自写报告）
- `--all` 必须搭配 `--hugo` 才会构建，搭配 `--deploy` 才会部署
- 转换时调用 `_validate_heading_structure()` 检测错位 `##` 子标题（两个 `##` 之间缺 `---` 分隔符，即 LLM 字段泄漏的子标题）与 h1 计数异常，**打印警告但不阻断转换**
- Hugo 构建成功时也输出 stderr（含 warning/info），便于发现构建过程中的问题

## 报告 heading 层级保障

报告由 `paper_report_generator.py` 生成，每篇论文是一个 `## ` (h2) 区块，内部字段标题为 `### ` (h3)，字段内子标题应为 `#### `/`##### `。LLM 输出的 heading 层级不可信，必须 re-leveling。

**处理路径**（2026-07-13 统一）：
- 4 个 LLM 摘要字段（motivation / key_setup_and_method / main_results_and_physics / take_home）统一经 `_process_results_markdown()` → 内部调 `_adjust_headings()` 将最低层级上移到 `base_level=4`（`####`）
- `abstract` / `one_sentence` 经 `_process_text_for_markdown()`（不期望出现 heading，不做 re-leveling）

**历史缺陷**：此前仅 `main_results_and_physics` 走 re-leveling 路径，其余 3 字段走 `_process_text_for_markdown` 直通。20260608 报告中 LLM 在 `key_setup_and_method` 字段输出 `## 核心驱动系统` 等子标题，未降级直通为 h2，导致 TOC 侧栏（只匹配 h2）将其列为独立论文条目，flex 布局下长 CJK+数学 token 串溢出页面。统一处理路径后根因消除。

## CSS 兜底（长 token 换行）

`assets/css/extended/custom.css` 中仅保留一条不可见的防御性规则：
```css
.post-content p, .post-content li { overflow-wrap: break-word; word-break: break-word; }
```
- PaperMod 原生 CSS 只对 `pre code` 设了 `word-break`，段落文本没有
- `overflow-wrap: break-word` 让长不可断行 CJK + KaTeX 内联数学 `\(...\)` token 串可换行，防止溢出
- **不改变任何视觉样式**，仅作为溢出兜底
- **未** 给 `.katex` 加 `white-space: normal`（会扭曲数学渲染）

## 样式定制

### 技术路线

PaperMod 主题的定制方式：

```
site/assets/css/extended/custom.css  →  Hugo 自动合并到 stylesheet.css（仅保留 overflow-wrap 兜底）
site/layouts/list.html               →  覆盖主题列表模板（卡片预览 .Description 优先）
site/layouts/partials/extend_head.html →  KaTeX 数学渲染脚本注入
```

> **文章页布局**：使用 PaperMod 原生 `single.html` + 原生 `toc.html`，不覆盖。原生 TOC 为可折叠 `<details>`，渲染在正文上方，匹配全部 h1-h6 生成嵌套目录。`ShowToc: true`（hugo.yaml 全局 + 每报告 front matter）控制是否显示，`TocOpen: true` 控制默认展开。

### 1. 卡片摘要 Description

报告中文章卡片默认显示 `.Summary`（自动截断正文前 70 字），因报告含 LaTeX 公式导致首页卡片显示脏内容。修改为优先使用 front matter `description`：

**转换脚本（`convert_reports_to_hugo.py`）**：
- `_build_description()` — 统计报告中的论文数（`##` 标题数量，排除`目录`）→ 生成 `"2026-06-22 — 共收录 29 篇相关论文"`
- `_build_front_matter()` — 写入 `description` 字段到 Markdown front matter

**列表模板（`layouts/list.html`）**：
- 卡片区域优先读取 `.Description`，不存在时才回退到 `.Summary`

### 2. 目录（TOC）

使用 PaperMod 原生 TOC，不自定义。原生行为：
- `layouts/_partials/toc.html` 匹配全部 `<h[1-6]>` 生成嵌套目录树
- 渲染为可折叠 `<details class="toc">`，位于正文上方
- `ShowToc: true` 显示，`TocOpen: true` 默认展开
- 报告中 h2=论文标题、h3=字段标题、h4/h5=字段内子标题，原生 TOC 会显示完整嵌套层级

> **历史**：曾自定义侧栏 TOC（flex 布局 + 260px sticky 侧栏 + scroll-spy），但 flex 布局导致长 CJK+数学 token 串溢出页面且难以换行。2026-07-13 回退到原生块级布局后问题消除。

### 3. 文章页正文宽度

使用 PaperMod 原生 `--main-width: 720px`，不覆盖。

> **历史**：曾用 `body:has(.post-single) .main { --main-width: 1100px; }` 加宽文章页，但与 flex 侧栏布局叠加后加剧了溢出问题。2026-07-13 回退到原生 720px。

### 每报告配置

转换脚本在每篇报告 front matter 写入：
```yaml
---
description: "2026-06-22 — 共收录 29 篇相关论文"
ShowToc: true
TocOpen: true
---
```

## 依赖

```bash
pip install ghp-import
# Hugo: https://gohugo.io/installation/
```

## crontab 环境注意事项

`run_weekly.sh` 使用全路径 Python + `set -euo pipefail`。crontab 下需要注意：

```bash
# crontab 极简 PATH（/usr/bin:/bin），不包含：
# - /usr/local/bin（hugo）
# - /path/to/paperscrawler-venv/bin（ghp-import）
# 修复：脚本内显式 export PATH
export PATH="/usr/local/bin:/path/to/paperscrawler-venv/bin:${PATH:-}"
```

# 数据库迁移模式

`init_db_papers()` 使用 `CREATE TABLE IF NOT EXISTS` 建表，随后对新版本新增的列用 `ALTER TABLE ADD COLUMN` 渐进式迁移：

```python
# db.py:222-262
mineru_columns = ["mineru_parse_status TEXT DEFAULT 'pending'", ...]
for col_def in mineru_columns:
    try:
        self.conn.execute(f"ALTER TABLE papers ADD COLUMN {col_def}")
    except sqlite3.OperationalError:
        pass  # 列已存在则跳过
```

迁移按功能分组：MinerU → Semantic Filter → Report Status。新增列时在此追加即可。

# 测试策略

采用两套测试体系分工协作：

## T1/T2 — pytest 自动化测试（`tests/`）

**目标**：保护重构安全，防止回归。**100% 离线，零跳过**。

| 层级 | 方法 | 覆盖范围 |
|------|------|---------|
| T1 纯逻辑 | 直接调用函数，无需 mock | DB CRUD、报告生成、关键词匹配、DOI 提取 |
| T2 模拟 I/O | `unittest.mock` 模拟网络层 | CrossRef API、DeepSeek API、SMTP 邮件 |

mock 数据来源：先通过 T3 真实测试捕获，固化在测试函数内联或 `tests/fixtures/` 中。

## T3 — 真实集成测试（`tests/real/`）

**目标**：验证模块与外部服务的真实连通性。

- 独立 Python 脚本（非 pytest），需 `.env` 配置
- 手动运行：`bash tests/real/run_all.sh`
- 捕获真实响应写入 `tests/fixtures/`，供 T2 测试使用
- 每次重构后手动跑一次，确认外部接口仍正常

# 架构改进 (2026-06-07)

## Phase 级异常保护

`runner.py` 中每个 phase 调用包裹 `try/except`，单个 phase 未捕获的异常记录 traceback 后继续下一 phase，不中断整个 pipeline。

## 配置原子写入

Web UI 的 6 个 save 端点统一使用 `_atomic_write()`（先写 .tmp 再 `os.replace()`），防止并发读写导致配置损坏。

## Logger 架构统一

`logging.basicConfig` 从 `base.py` 移入 `main.py`（CLI 入口）和 `web/app.py`（Web 入口），各 phase 模块使用 `logging.getLogger(__name__)` 获取各自 logger，日志中可区分来源。支持 `LOG_LEVEL` 环境变量控制级别。

## 配置热加载

`config.py` 新增 `reload_config()` 函数，Web UI 修改 YAML 配置后自动调用，无需重启进程即可刷新 `SKIP_PHASE_*`、`LLM_API_CONFIG_*`、`SUMMARIES_PROMPT` 等所有运行时变量。

## journal_overrides 工具共享

`JOURNAL_OVERRIDES_PATH` 移至 `config.py`，`load_journal_overrides()` 和 `journal_effective()` 移至 `pipeline/base.py`，消除 `phase_a.py` 和 `web/app.py` 中 ~35 行重复代码。

## mineru_fulltext 列去除冗余存储

Phase E2 不再向数据库 `mineru_fulltext` 列写入全文文本（文本已存在于 `data/mineru_output/{doi}/full.md`）。Phase F 改为从文件直接读取，避免 SQLite 因大量全文数据急剧膨胀。

## force 参数语义简化 (P2)

`runner.py` 的 `run_phases(force=True)` 表示忽略 SKIP_PHASE_* 配置运行全部阶段。
`use_overrides` 参数已移除（配套的 `skip_overrides.json` 已删除）。`run_pipeline(run_all=True)` 等效于 `run_phases(force=True)`，`force` 保留兼容。

# WebUI 历史演进（已移除功能）

2026-07-26 起 WebUI 收敛为只读 Dashboard、Papers 与 Report 页面；此前的 SSE 日志流、子进程运行控制和
Config 页面均已删除。运行、配置修改和邮件模板选择应通过 CLI、YAML 配置文件及
`DATA_DIR/email_template_override.txt` 完成。历史实施过程保留在 `docs/tasks.md`。

## 两阶段相关性与全文下载安全

Phase E 只用标题和摘要做高召回筛选，结果写入 `relevance_screen_*`。只有 A/B/C 和低置信度 D 进入 E2；高/中置信度 D 直接写入最终 D。E2 在 `fulltext_download_events` 中用 `BEGIN IMMEDIATE` 原子占位，按 Asia/Shanghai 自然日限制总尝试 3 篇、单 publisher 2 篇，失败也占额。同一 DOI 当天只能占位一次；队列按新论文优先、A→B→C→low-D 排序，历史回填仅使用剩余额度。

E3 对短正文使用全文；长正文按 `llm.fulltext_relevance.evidence_max_chars` 提取引言、结论、章节标题和领域关键词窗口。最终结果写入 `llm_relevance_*`：高/中置信初筛 D 使用 `abstract_clear_reject`；有全文的候选使用 `fulltext`。A/B/C 与低置信 D 在 `mineru_parse_status` 为 `pending`、`failed` 或 `skipped` 时都保持最终相关性 pending，等待 daily 自动重试或用户手动导入 PDF，绝不以摘要进入报告。

新增表 `fulltext_download_events(id, doi, publisher, local_date, attempted_at, status, error)` 作为配额审计日志。新增 `relevance_screen_*` 列保存初筛快照，`relevance_screen_is_backfill` 区分历史回填与新论文；旧 `llm_relevance_*` 始终表示最终判定，保持 WebUI 和报告查询兼容。

A 必须有核心对象的正向证据：激光驱动离子/质子、激光靶及直接诊断、后加速、激光驱动粒子紧凑束线、等离子体波导/通道形成演化与表征，或以束流辐照效应/剂量/损伤机制及明确下游应用为主贡献。聚变/低温靶注入不能判 A；只有实际展示高重复频率激光聚焦条件下可迁移的靶输运/注入才可判 B。非激光聚变、Z-pinch/DPF 论文只有在实际展示可迁移的 FLASH/MHD 算法、鞘层跟踪或合成诊断时才可判 B，单纯提及工具名不算。B 必须是论文实际展示的具体可迁移映射；仅同大领域、背景提及应用或“可能有用”是 C。
