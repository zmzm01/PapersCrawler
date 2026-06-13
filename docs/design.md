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
│   ├── models/                  # sentence-transformers 本地模型
│   └── session_cached/          # 浏览器 Session 缓存 (按 publisher 分子目录)
├── docs/                        # 设计文档、数据源调研、API 参考
│   ├── doc-设计.md               # 本文 — 需求与架构设计
│   ├── doc-任务.md               # 执行步骤、关键决策、经验教训
│   ├── doc-MinerU-Usage.md      # MinerU API 使用参考
│   └── doc-Data-Sources-Invest.md  # 数据源调研记录
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
│       ├── templates/           # Jinja2 模板 (5 页面)
│       │   ├── base.html        #   布局模板
│       │   ├── dashboard.html   #   状态概览
│       │   ├── pipeline.html    #   流水线控制 + SSE 日志
│       │   ├── report.html      #   报告生成
│       │   ├── logs.html        #   日志查看
│       │   └── config.html      #   配置展示
│       └── static/
│           ├── css/style.css
│           └── js/app.js
├── tools/                       # 辅助工具
│   ├── reset_pipeline.py        # 重置流水线状态（5 子命令 + --publisher 过滤）
│   ├── convert_md_to_pdf.py     # Markdown → PDF (pandoc + cloakbrowser 主路径)
│   ├── reset_empty_abstract.py  # 重置空摘要论文的 Phase D/E/G
│   ├── debug_llm_summary.py     # 诊断 LLM Summary JSON 解析失败
│   ├── debug_publisher_urls.py  # 诊断 Publisher URL 抓取（headful 浏览器）
│   ├── schedule_daily.py        # 每日调度入口（A→F，支持 --no-reset-* 开关）
│   ├── schedule_weekly.py       # 每周调度入口（G→H）
│   ├── migrate_db_v2.py         # 数据库迁移 v2（新增 skipped_dois 表）
└── README.md                    # 项目使用说明
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

整个项目以 SQLite 数据库为中心，按 8 个阶段顺序执行。每个阶段读取上一阶段的输出，处理后写入数据库。

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
Phase D: 语义相似度参考排序 (sentence-transformers, 可选)
      │  余弦相似度 → 仅存分数供 WebUI 排序，不参与过滤
      ▼
Phase E: LLM 相关性判断 (DeepSeek)  ← 四级分类 A/B/C/D
      │  → 类别 A: 直接相关 (核心方向)
      │  → 类别 B: 间接相关 (技术/方法可迁移)
      │  → 类别 C: 同领域但距离较远
      │  → 类别 D: 基本无关
      │  仅 A/B 进入下游, C/D 终止
      ▼
Phase E2: MinerU PDF 全文解析
      │  下载 PDF → MinerU API → 提取 Markdown 全文
      ▼
Phase F: LLM 论文总结 (DeepSeek)
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
  │    Phase D: semantic_filter_*       → 语义相似度             │
  │    Phase E: llm_relevance_*         → LLM 相关性            │
  │    Phase E2: mineru_parse_*         → MinerU PDF            │
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

**语义相似度** (Phase D) — 三列：`semantic_filter_status` / `_error` / `_date`
- `semantic_similarity_score`, `semantic_best_subdomain` (排序参考，不参与过滤)

**LLM 相关性** (Phase E) — 三列：`llm_relevance_status` / `_error` / `_date`
- `llm_relevance_category` (TEXT: A/B/C/D) — 四级分类，替代已废弃的 `llm_relevance_result`
- `llm_relevance_subfields` (TEXT: JSON 数组) — 匹配的子领域列表
- `llm_relevance_confidence`, `llm_relevance_reason`
- `llm_relevance_result` (INTEGER, **已废弃**) — 旧版二分类 0/1，`reset-relevance --all` 后不再写入

**MinerU 全文** (Phase E2) — 三列：`mineru_parse_status` / `_error` / `_date`
- `mineru_output_dir` — 解析输出目录相对路径（如 `data/mineru_output/10_1103_xxx/`）
- `mineru_fulltext` — 已废弃，不再写入。Phase F 直接从 `mineru_output_dir/full.md` 读取全文

**LLM 总结** (Phase F) — 三列：`llm_summary_status` / `_error` / `_date`
- `llm_summary_result` (JSON 字符串)

**报告状态** (Phase G) — 两列：`report_status` / `report_date`
- `report_date` 是主要过滤条件：`get_papers_for_report()` 使用 `report_date IS NULL` 查询未报告论文
- `report_status` 保留为辅助标记，`mark_papers_reported()` 同时写入两者
- 支持 `reset-report --days N` 按日期范围重置，方便同一天重试

**时间戳** (全局)
- `created_date`, `updated_date`

**状态值**：`FetchStatus` 枚举 (`pending` → `success` / `failed` / `skipped`)

### subscribers 表（邮件订阅者）

```
subscribers:
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  email           TEXT UNIQUE NOT NULL      -- 订阅邮箱
  name            TEXT DEFAULT ''           -- 订阅者姓名（可选）
  active          INTEGER DEFAULT 1         -- 1=启用, 0=停用
  delivery_method TEXT DEFAULT 'email'      -- 投递方式 (预留: email/webhook/wechat)
  created_date    TEXT                      -- 创建时间
  updated_date    TEXT                      -- 更新时间
```

Phase H（邮件推送）优先使用 `subscribers` 表中 `active=1` 的邮箱列表作为收件人。当表中无订阅者时，回退到 `.env` 的 `SMTP_TO_ADDRS` 配置，保证向后兼容。

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

## 1. Phase D 作为参考排序（不再参与过滤）

Phase D 的语义相似度计算仅用于 WebUI Papers 页面的排序参考，**不再**决定论文能否进入 Phase E。`SKIP_PHASE_D = True` 为默认值（跳过），所有论文直接走 Phase E LLM 判断。开启时：
- 计算余弦相似度 + 记录最佳匹配子领域
- 分数存入 `semantic_similarity_score` + `semantic_best_subdomain`
- 始终标记 `semantic_filter_status = 'success'`，不修改 `llm_relevance_status`

原因：论文量级小（每轮 ~200-400 篇），DeepSeek API 成本极低（约 $0.08/轮），Phase D 的 API 节省收益远不如 LLM 判断精度重要。

## 2. Phase F 不全文回退

Phase F（LLM 总结）仅处理有 MinerU 全文的论文。无全文字段直接标记 `skipped`，**不**回退使用标题+摘要。原因：
- 摘要信息密度不足，LLM 总结质量不可控
- 避免「有总结但质量差」的误导性结果

## 3. Phase E/F 并发策略

使用 `ThreadPoolExecutor` + 共享 `LLM_CONCURRENT_MAX` 配置：
- 主线程负责 prompt 构建和 DB 写入（无网络 I/O）
- 子线程仅做纯 API 调用
- 单论文失败不影响整体流程（逐篇 try/except）

## 4. Publisher 爬虫的持续性上下文

使用 cloakbrowser 驱动 headful Chromium 和持久化 browser context：
- 同一 publisher 共用一个 session（`data/session_cached/<publisher>/`）
- cloakbrowser 自动处理浏览器指纹伪装，无需手动注入反检测 JS
- 失败熔断：连续失败 `PUBLISHER_MAX_CONSECUTIVE_FAILURES` 篇后自动中止，避免 IP 封禁

## 5. Phase E2 PDF 下载策略

`BasePublisherScraper.download_pdf()` 负责 PDF 下载（详见「流水线子阶段详解」）：
- 先 `goto(page_url)` 建立浏览器上下文（cookie/session/referrer）
- 扫描 DOM 中 `<a>PDF</a>` 提取同域 URL（解决 APS 跨域问题）
- 先尝试 `requests` + 浏览器 cookies/UA 下载（最快，避免 AIP 等 CSP 拦截）
- 失败则降级为 `page.evaluate(fetch)` 兜底（完全继承浏览器上下文）
- 下载后**立即保存**到 `data/mineru_output/<safe_doi>/paper.pdf`，再传给 MinerU 解析
- 保存前校验 `%PDF-` 头部，非 PDF 内容直接报错

**关键设计**：PDF 先保存再解析，确保 MinerU 上传失败时 PDF 不丢失。不再使用 tempfile。

## 6. 逐阶段错误隔离

每个阶段用独立 `try/except` 包裹单篇论文的处理。一篇失败不影响同阶段其他论文，一阶段失败不影响后续阶段（依赖的数据为空则后续阶段自然跳过）。

## 7. 数据库驱动的状态机

流水线不依赖内存状态，所有进度持久化到 SQLite：
- 中断后重启自动从断点继续
- `MAX_PAPERS_PER_PHASE` 支持单阶段调试
- `reset_pipeline.py` 提供精细化的状态重置（支持按 publisher 过滤）

## 8. 共享数据模型（src/common.py）

跨模块共享的 `Paper` dataclass 和 LLM 异常集中在 `src/common.py`，避免循环导入和重复定义：
- `Paper` 被 RSS 和 Publisher 同时使用
- LLM 异常被 `PaperRelevanceChecker` 和 `DeepSeekPaperSummarizer` 共享
- 各模块特有的异常（`PageParseError`、`NotFoundError`）保留在各自模块

## 9. 自动报告与用户报告分离

自动流水线生成的日报（Phase G）和 Web UI 用户勾选生成的报告写入不同目录，避免邮件推送误发用户报告：

| 维度 | 自动报告 (Phase G) | 用户报告 (Web UI) |
|------|-------------------|-------------------|
| 输出目录 | `data/reports/auto/` | `data/reports/user/` |
| 文件名 | `report_YYYYMMDD.md`（同日期覆盖） | `report_YYYYMMDD_HHMMSS.md`（不覆盖） |
| 标记已报告 | 是 | **否** |
| 邮件推送 | 是（Phase H 读取 `auto/`） | 否 |

Phase H 检测逻辑：
1. 若有 `report_path` 参数（WebUI 发送日报）→ 直接发送指定报告，无更新通知模式禁用
2. 否则检查 `auto/report_YYYYMMDD.md` 是否存在
3. 存在 → 作为附件发送，正文使用 HTML 模板渲染
4. 不存在 → 发送无更新通知（同样使用 HTML 模板）

**报告论文数量统计**：使用 `re.findall(r'(?m)^## (?!目录)[^#]', ...)` 精确匹配报告中的 `## ` 标题行，排除 `### ` 子节和 `## 目录`（TOC 标题），避免 `str.count("## ")` 的误计。

**HTML 邮件模板**：`templates/email/default.html`（正式风格）、`templates/email/funny.html`（搞笑风格）和 `templates/email/detailed.html`（详细版，含追踪期刊、筛选依据、Publisher 抓取状态）
- 使用 `str.format()` 渲染，不引入新依赖
- 模板变量：`{report_title}`（邮件标题）、`{paper_msg}`（论文数量或无新增提示）、`{attachment_section}`（附件标记 HTML，无论文时为空）、`{journal_list}`（追踪期刊列表 HTML）、`{keyword_list}`（关键词标签云 HTML）、`{domain_block}`（完整领域定义 HTML）、`{publisher_stats}`（Publisher 抓取状态表 HTML）
- 报告作为附件，正文无论文列表
- 模板名可在 `configs/settings.yaml` 的 `email.template` 配置，WebUI Config 页面可通过 `<select>` 下拉框覆盖
- 当 `email_template_override.txt`（`DATA_DIR/` 下）存在时，WebUI 优先使用其内容作为模板选择

**Publisher 抓取状态**（`detailed.html` 特有）：显示过去 7 天各 publisher 的爬取健康状况。
- 仅展示 `publishers.yaml` 中至少有一个期刊 `enabled: true` 的 publisher（禁用 publisher 如 Optica 不显示）
- 状态判断：失败数 ≥ `PUBLISHER_MAX_CONSECUTIVE_FAILURES`（默认 3）→ "🚫 Blocked"，否则 "✅ OK"
- `pending` 论文是熔断器残留（Phase C 同 publisher 连续失败 N 篇后自动中止），不纳入统计

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

使用结构化字典格式（`scope_definition` + `irrelevant_fields` + `sub_domains_embedding`）：

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
sub_domains_embedding:
  laser_wakefield_acceleration: >
    Plasma-based wakefield acceleration driven by intense laser pulses...
```

### 字段分工

| 字段 | 用途 | 语种 | 要求 |
|------|------|------|------|
| `scope_definition` | Phase E LLM prompt — 完整领域定义 | 中文 | 每子域含 `description`（段落描述）+ `topics`（展开关键词列表） |
| `irrelevant_fields` | Phase E LLM prompt — 降低误判 | 中文 | 定义"不相关"边界 |
| `sub_domains_embedding` | Phase D 语义相似度 | **仅英文** | 每段 < 300 words，简练自然语言，供 sentence-transformers 编码 |

`scope_definition` 的子域可独立注释，不关注的域直接 YAML 注释即可。

### Phase E Prompt 构建流程

```
keywords.yaml:
  scope_definition (6 sub-domains)
  irrelevant_fields
          ↓
  src/config.py: build_scope_block()
          ↓
  Plain text block with ## headers + bullet lists
          ↓
  configs/prompts/relevance.yaml template (scope_block placeholder)
          ↓
  LLM: classification task with Steps 1-4, JSON output
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

> **Web UI 是 Pipeline 监控仪表盘 + 报告工作站，不是 CLI 的替代品。**

| CLI 擅长 | Web UI 擅长 |
|----------|------------|
| 定时/自动化运行（cron） | 可视化监控：一眼看清各阶段状态分布 |
| ad-hoc 重置/调试（reset 工具） | 精准控制：Config 页切换 SKIP → Pipeline 页按钮灰显 |
| 深度调试（debug 脚本） | 交互式报告：勾选论文、预览、下载（CLI 做不到） |
| 批量全流程 | 配置编辑：领域描述文本框 + 连通性测试 + 期刊启用开关 |

### 配置隔离原则

- **CLI** 的 SKIP 配置完全由 `src/config.py` 控制，不受 Web UI 影响
- **Web UI** 的 SKIP 切换写入 `data/skip_overrides.json`，仅影响 Pipeline 页的按钮状态
- 两者互不干扰，无暗规则

## 页面功能

| 页面 | 路由 | 功能 |
|------|------|------|
| Home | `GET /` | 项目介绍、论文/出版社统计、快速入口 |
| Pipeline | `GET /pipeline` | 10 阶段 Run/Reset 按钮（A-RSS / A-CR 独立）+ 状态图表（CSS 柱状图）+ SSE 实时日志（支持级别过滤）+ 子进程执行。被 Config 跳过的阶段按钮灰显不可点击 |
| Papers | `GET /papers?sort=created\|published` | 论文列表，默认按入库日期降序，可选按发表日期排序（显示精度警告）。展示语义相似度分（可选）和 LLM 相关性状态 |
| Report | `GET /report` | 勾选有 LLM 总结的论文 → 生成 Markdown 报告（写入 user/ 目录）→ 浏览器预览 + 下载 |
| Data Sources | `GET /datasources` | 期刊启用/禁用表格，每个期刊可独立控制 RSS 和 CrossRef 数据源开关。更改保存到 `data/journal_overrides.json`，不修改 publishers.yaml |
| Logs | `GET /logs` | 日志查看（支持级别过滤，修复 innerHTML bug） |
| Subscriptions | `GET /subscriptions` | 邮件订阅者管理（添加/删除/启用停用/发送测试邮件/从 .env 导入），Phase H 优先使用 DB 订阅者列表；"发送日报"按钮通过 `POST /subscriptions/send-report` 直接调用 Phase H |
| Config | `GET /config` | SKIP 开关切换（影响 Pipeline 页按钮）+ 研究领域描述文本框 + 连通性测试（DeepSeek/CrossRef/MinerU 一键测试）+ MinerU Token 过期色标 + YAML 编辑器（语法校验 + 二次确认） |

## 任务执行模型

- 点击 Run → `POST /pipeline/run/{phase}` → FastAPI 后台线程启动子进程 → 子进程调用 `pipeline.runner.run_phases(force=True)` → 写日志到同一文件
- Config 页跳过的阶段：Pipeline 页按钮灰显、`POST /pipeline/run/{phase}` 返回 400、子进程自动跳过
- `_phase_lock`（asyncio.Lock）确保同一时间只有一个阶段在运行
- 前端通过 SSE (`GET /pipeline/logs`) 接收实时日志推送

## Reset 级联逻辑

| 阶段 | 重置列 | 级联 | 条件 |
|------|--------|------|------|
| A-RSS / A-CR | 无（Phase A 无状态列，仅做发现） | — | — |
| B | cr_metadata_fetched | — | 所有非 pending |
| C | publisher_page_fetched | — | 非 pending 且非 NonResearchPageError |
| D | semantic_filter (仅语义分, 不触 LLM) | — | 所有非 pending |
| E | llm_relevance | — | 所有非 pending |
| E2 | mineru_parse + llm_summary + report | llm_summary, report | 所有非 pending |
| F | llm_summary + report | report | 所有非 pending |
| G | report_status + report_date | — | reported |

## 启动方式

```bash
# 桌面环境
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
| `data/skip_overrides.json` | Web UI Pipeline 页 | Config 页 Toggle 按钮写入此文件。跳过的阶段按钮灰显 + 后端拒绝执行 |

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

`call_llm_api_with_retry()` (`src/common.py`) 共用封装，提供 2 次重试 + 1s 退避。所有 LLM 调用（Phase E 相关性、Phase F 总结、FormulaFixer）统一使用。

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

配套工具 `tools/reset_empty_abstract.py` 可将已入库空摘要论文的 Phase D/E/G 重置为 pending，触发重新评估。

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
- 关键词表：`Erratum`, `Comment on`, `Response to`, `Publisher's Note`
- 实现位置：`pipeline/phase_c.py` 的 retry 循环内，`parse_page()` 成功后检查

### 触发后的行为

NonResearchPageError 触发后，Phase C 会执行：
1. 写入 `skipped_dois` 表（记录 DOI + 原因 + 时间），防止将来被重新发现
2. 调用 `db.delete_paper()` 从 `papers` 表中删除该记录

这与 `AcceptedPaperError` 不同——Accepted Paper 仅删除不记入 `skipped_dois`，
因为同 DOI 的正式版论文会在未来出现，届时 Phase A 应能正常发现。

删除后论文在下次 RSS/CrossRef 发现时会被 `is_doi_skipped()` 阻止，不再重复处理。

### 与空摘要论文的区别

| 类型 | Phase C 行为 | Phase D 行为 | Phase E 行为 |
|------|-------------|-------------|-------------|
| **非论文页**（Erratum 等） | 直接 `delete_paper()` 删除 | — | — |
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

## 9. APS Accepted Paper 跳过（AcceptedPaperError）

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
3. 级联跳过 Phase D（语义过滤）和 Phase E（LLM 相关性）——判定其相关性无意义，因为即使相关也无法总结
4. 后续阶段（Phase E2/F/G/H）自然跳过

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
| **A** | 直接相关 | 直接研究课题组核心方向的理论/实验/模拟 | → E2/F/G/H |
| **B** | 间接相关 | 相关技术或方法，对课题组有潜在参考价值 | → E2/F/G/H |
| **C** | 同领域但远 | 同属加速器/等离子体领域，但与核心兴趣距离较远 | 终止，不进入下游 |
| **D** | 基本无关 | 不属于课题组关注范围 | 终止，不进入下游 |

Phase E2（MinerU PDF 解析）、Phase F（LLM 总结）、Phase G（报告生成）仅在论文被标记为 **A 或 B** 时执行。C 类论文保留在数据库中供人工复核。

### 匹配子领域记录

LLM 同时输出 `MatchedSubfields`（JSON 数组），记录论文命中了 `scope_definition` 中哪些子领域。此信息存储在 `llm_relevance_subfields` 列，供 WebUI Papers 页展示和后续分析。

### Prompt 策略

Prompt 使用 `configs/keywords.yaml` 中的 `scope_definition`（完整的中文领域定义，含 6 个子域的段落描述 + 展开关键词列表）和 `irrelevant_fields`（不相关领域边界），由 `config.build_scope_block()` 格式化为带标题的分节文本块，嵌入 `configs/prompts/relevance.yaml` 模板。

LLM 被要求执行 4 个步骤：
1. 判断论文属于 scope_definition 中哪些子领域
2. 分配相关性类别 A/B/C/D
3. 给出置信度 high/medium/low
4. 简要说明判断理由

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

### 工具支持

`tools/delete_accepted_papers.py` 用于清理存量数据：
```bash
python tools/delete_accepted_papers.py --dry-run   # 预览
python tools/delete_accepted_papers.py              # 交互确认
python tools/delete_accepted_papers.py --force       # 直接执行
```

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

`tools/schedule_daily.py` 在调用 `run_daily()` 前自动重置
`publisher_page_fetched_status = 'failed'` 为 `pending`，
使因 Cloudflare 瞬态拦截等偶发原因失败的论文在每次每日运行时自动获得重试机会。
仅重置 `failed` 状态，不触碰 `skipped`。

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

# 流水线子阶段详解

## Phase C — Publisher 页面抓取

使用 cloakbrowser 驱动 headful Chromium 和持久化 browser context：
- 同一 publisher 共用一个 session（`data/session_cached/<publisher>/`）
- cloakbrowser 自动处理浏览器指纹伪装，无需手动注入反检测 JS
- 页面间随机延迟 `PUBLISHER_PAGE_DELAY_MIN~MAX`（默认 3-5s），publisher 间冷却 15s
- 失败熔断：连续失败 `PUBLISHER_MAX_CONSECUTIVE_FAILURES`（默认 3）篇后自动中止，避免 IP 封禁
- **Publisher 启停检查**：运行前从 `publishers.yaml` 构建 `enabled_publishers` 集合，
  禁用 publisher 的 pending 论文直接标记 `skipped`，不浪费浏览器启动时间（详见「韧性策略 #12」）
- **Pre-fetch 非研究论文检测**（`configs/settings.yaml` 配置）：在浏览器启动之前根据 DB 中的论文标题进行前缀匹配（`startswith`），匹配到 `erratum`、`author correction:`、`publisher correction:`、`comment on`、`response to`、`publisher's note` 等关键词时直接 `delete_paper()` + `insert_skipped_doi()`，避免浏览器启动和重试消耗。pre-fetch（`prefetch_non_research`）和 post-fetch（`postfetch_non_research`）有独立开关，关键词列表（`non_research_keywords`）由用户配置
- **Bot 拦截检测**（parse_page 之后）：仅当 `parse_page()` 返回空结果（title+doi+abstract 全空）时才检查 bot 标记；
  检测范围包括：
  - Cloudflare: `challenge-platform`、`_cf_chl_opt`、`cf-browser-verification`、`cf-ray` + 短 HTML、`turnstile` + `challenge`
  - Radware Bot Manager: `radware`、`bot manager`（HTML 和页面标题）
  - Captcha 页面标题: `captcha`
  - Nature Client Challenge (JS 验证): `javascript is disabled`（HTML 内容）、`client challenge`（页面标题）
  - 异常处理中也增加 bot 检测（含页面标题提取），bot 拦截导致的异常走完整重试而非 attempt 0 终止
- 按 publisher 分组处理，同一组复用浏览器实例（`SCRAPER_MAP` 管理 7 个 publisher）
- Session 缓存自动清理：`BasePublisherScraper.close()` 在每次 publisher 组处理完毕后
  执行 `shutil.rmtree()` 清理 Chromium profile 目录（详见「韧性策略 #9」）
- 错误诊断：`fetch_page()` 异常时自动保存 HTML 快照到 `data/raw/page/error/`
  （详见「韧性策略 #10」）

7 个 Scraper 子类各适配不同的页面结构（meta 标签 / JSON-LD / XPath）。

### Optica 反爬注意事项

当前 `configs/publishers.yaml` 中 `optica` 和 `opex` 均为 `enabled: false`（默认禁用）。如需启用，
请注意以下已知问题：

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

### 下载优先级（2026-06-07 优化）

```
requests + 浏览器 cookies (主, 秒级失败)
  └── 失败 → JS fetch (兜底, 完整浏览器上下文)
```

**主路径：requests + 浏览器 cookies**
从浏览器 context 提取登录态 cookies + User-Agent，用 Python requests 做 HTTP 直连下载。
比 JS fetch 更快的理由：
- **不受 CSP 限制** — AIP 的 `connect-src` 策略拦截 JS `fetch()`，但 requests 直接通过
- **无浏览器 JS 执行开销** — 秒级返回失败状态（vs JS fetch 需等 60s 超时才降级）
- **User-Agent 降级保护** — `navigator.userAgent` 获取失败时使用硬编码 Chrome 120 UA 兜底
- **覆盖所有 publisher** — 同域 PDF URL + 浏览器 cookie 认证

**兜底：JS fetch**
- 仅当 requests 路径不可用时触发（预期极少发生）
- 使用 `page.evaluate(fetch(pdf_url))` 继承完整浏览器上下文
- 保留此路径应对未来可能出现的要求完整 JS 环境才能下载的 publisher

### PDF 复用

`phase_e2.py` 支持已下载 PDF 的本地复用，避免重复下载：

1. 进入处理前检查 `data/mineru_output/<safe_doi>/paper.pdf` 是否存在
2. 存在 → 读取前 5 字节校验 `%PDF-` 头部 + 非空检查
3. 校验通过 → 跳过下载，直接传入 `parser.parse_pdf()` 开始 MinerU 解析
4. 校验失败（文件损坏/非 PDF）→ 删除后重新下载覆盖

此设计与「PDF 立即保存」配合生效：MinerU 上传失败后重跑 Phase E2 时，已保存的 PDF 直接复用，不重复下载。

### APS 导航容错

APS 使用 `link.aps.org` → `journals.aps.org` 双域名架构，goto 后的二次导航可能
在任何时刻销毁执行上下文。`download_pdf()` 包含三层防护：

| 层 | 防护 | 失效时 |
|----|------|--------|
| 1 | `wait_for_timeout(15000)` 等待充分稳定 | 进入第 2 层 |
| 2 | `for _attempt in range(2)` + except 重试 | 保留原始 `pdf_url`（跨域） |
| 3 | 主路径 requests+cookie 全局兜底（第 2 层非必需——即使没提取到同域链接，requests 也可用原始 URL） | JS fetch 兜底 |

### 已弃用的尝试（记录教训）

- `page.goto(pdf_url) + response.body()` — 浏览器 PDF viewer 以 stream 消费响应体，
  `response.body()` 返回 None（不等缓冲就消费了）
- `<a click> + page.expect_download()` — 程序化 `element.click()` 不被视为"用户手势"，
  `event.isTrusted=false`，不触发下载事件

## Phase F — LLM 结构化总结

- 仅处理有 MinerU 全文 **且** Phase E 判定为 A/B 类的论文（无全文或 C/D 类直接标记 skipped）
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

**传统路径 A**：`tools/convert_md_to_pdf.py` — pandoc → HTML → cloakbrowser → PDF
1. `pandoc --mathml --standalone` 生成含 MathML 的 HTML
2. cloakbrowser 加载 HTML，打印为 PDF
3. ⚠️ **已知问题**：`\(`/`\[\]` 公式渲染空白（MathML 无法解析 LaTeX 定界符）

**传统路径 B**：`src/processors/pdf_converter.py` — pandoc + xelatex
- 策略 A：自定义 LaTeX 模板（含 `xeCJK`、`Noto Sans CJK SC`、`\times` 兼容宏）
- 策略 B：无模板回退（适用于纯英文场景）
- 返回 `None` 表示失败（不抛异常）

# reset 工具族

`tools/reset_pipeline.py` 提供 6 个子命令，每个支持 `--publisher` 过滤：

| 命令 | 重置范围 | 默认条件 | 级联 | 典型用途 |
|------|---------|---------|------|---------|
| `reset-semantic` | `semantic_filter_*`, `semantic_similarity_score`, `semantic_best_subdomain`（5 列） | **全部**（无 status 过滤） | 无 | 修改 sub_domains 后 |
| `reset-relevance` | `llm_relevance_*`（6 列） | `failed`/`skipped`（`--all` 含 success） | 无 | 修改 scope_definition 后 |
| `reset-publisher` | `publisher_page_fetched_status/error`（2 列） | `failed`/`skipped`（跳过 NonResearchPageError） | 无 | 重试被 CF 拦截的论文 |
| `reset-mineru` | `mineru_parse_*`（5 列） | `failed`/`skipped` | 无 | 重试 PDF 解析失败的论文 |
| `reset-summary` | `llm_summary_*`（4 列） | `failed`/`skipped`（`--all` 含 success） | 无 | 修改 prompt 后重生成总结 |
| `reset-report` | `report_status/date`（2 列） | `reported`（`--today`/`--days` 按日期） | 无 | 重新汇入下次报告 |

关键设计：
- `reset-semantic` **不重置** LLM 相关性、MinerU 和 LLM Summary（语义分仅用于排序参考，不影响判断结果）
- `reset-relevance` **不级联** E2/F/G（相关性结果不影响已有 MinerU 全文和 LLM 总结）
- `reset-publisher` **跳过** `NonResearchPageError` 条目（非论文页面重试无意义）
- `reset-mineru` / `reset-summary` 重新解析/总结后，下游状态为 pending 的被自动拾取（无需显式级联）
- 所有命令执行前打印影响行数，交互确认后才执行

# 调试工具

| 工具 | 用途 |
|------|------|
| `tools/debug_llm_summary.py <doi>` | 调试 LLM Summary JSON 解析失败，打印错误上下文 |
| `tools/debug_publisher_urls.py` | 用 headful 浏览器诊断 Publisher URL 抓取问题 |
| `tools/reset_empty_abstract.py` | 重置空摘要论文的 Phase D/E/G 状态 |

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

## force 参数语义拆分

`runner.py` 中 `run_phases(use_overrides=True)` 表示加载 `skip_overrides.json`，`run_pipeline(run_all=True)` 表示忽略 SKIP 运行全部阶段。`force` 参数保留兼容但标记 deprecated。

# WebUI 改进 (2026-06-10)

## SSE 首尾日志推送

`_log_event_stream()` 首次连接时发送日志文件尾部 ~200KB 已有内容，让用户立即看到历史日志而非等待新日志产生。之后按增量方式推送新追加的行。

## 子进程日志修复

`_run_phase_subprocess()` 中：
1. **子进程 logging 配置**：子进程启动时调用 `logging.basicConfig()` 配置 `FileHandler` + `StreamHandler(sys.stderr)`，确保子进程的日志写入共享日志文件
2. **移除 `capture_output=True`**：子进程 stderr 直接输出到终端，与父进程共享日志流
3. **状态日志**：父进程记录子进程的启动、完成码、超时、异常等生命周期事件

## WebUI 缺失 logger 补全

`src/web/app.py` 中在 `logging.basicConfig()` 后添加 `logger = logging.getLogger(__name__)`，消除后端 6 处 `NameError: name 'logger' is not defined` 崩溃风险。

## Email Template 下拉选择器

Config 页面将文本输入框替换为 `<select>` 下拉框，自动从 `templates/email/*.html` 扫描可用模板。空选项 = 使用 `settings.yaml` 默认配置。选择保存在 `DATA_DIR/email_template_override.txt`，与 `settings.yaml` 的 `email.template` 叠加生效。
