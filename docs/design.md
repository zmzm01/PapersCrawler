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
│   ├── keywords.yaml            # 研究领域关键词表 + 段落描述
│   ├── email.yaml               # SMTP 邮件推送配置（含真实凭证，请勿提交）
│   └── prompts/                 # LLM Prompt 模板目录 (预留)
├── data/
│   ├── papers.db                # SQLite 数据库 (自动生成)
│   ├── PaperCrawler.log         # 运行日志
│   ├── raw/
│   │   ├── rss/                 # RSS Feed XML 缓存
│   │   └── page/                # Publisher 页面 HTML 缓存 (调试用)
│   ├── reports/                 # 生成的 Markdown 报告
│   ├── mineru_output/           # MinerU PDF 解析输出 (按论文子目录)
│   ├── models/                  # sentence-transformers 本地模型
│   └── session_cached/          # 浏览器 Session 缓存 (按 publisher 分子目录)
├── docs/                        # 设计文档、数据源调研、API 参考
│   ├── doc-设计.md               # 本文 — 需求与架构设计
│   ├── doc-任务.md               # 执行步骤、关键决策、经验教训
│   ├── doc-MinerU-Usage.md      # MinerU API 使用参考
│   └── doc-Data-Sources-Invest.md  # 数据源调研记录
├── slides/                      # 报告/演示文稿区域 (预留)
├── tests/                       # 单元测试
│   ├── conftest.py              # pytest 配置 + 自定义 markers
│   ├── test_db.py               # 数据库操作
│   ├── test_rss.py              # RSS 解析
│   ├── test_crossref.py         # CrossRef 元数据
│   ├── test_publisher_parse.py  # Publisher 页面解析
│   ├── test_relevance.py        # 相关性判断
│   ├── test_report.py           # 报告生成
│   ├── test_pdf.py              # PDF 转换
│   └── test_email.py            # 邮件发送
├── src/
│   ├── common.py                # 共享数据模型 (Paper dataclass) + 共享异常
│   ├── config.py                # 全局配置 (路径、密钥来自 .env)
│   ├── main.py                  # 主入口 — 8 阶段流水线
│   ├── sources/
│   │   ├── rss.py               # RSS Feed 抓取与解析 (返回 Paper dataclass)
│   │   ├── crossref.py          # CrossRef DOI 元数据查询 (返回 PaperMetadata)
│   │   └── publisher.py         # 7 个出版社的 cloakbrowser 页面抓取器
│   └── utils/
│       ├── db.py                # SQLite 数据库 CRUD + FetchStatus 枚举
│       ├── paper_relevance.py   # 语义过滤器 + LLM 相关性判断 (SemanticFilter / PaperRelevanceChecker)
│       ├── llm_summarize_deepseek.py  # DeepSeek API 论文总结 + LLMFormulaFixer
│       ├── paper_report_generator.py  # Markdown/HTML 报告生成 + 标题重定级
│       ├── mineru_paper_parser.py     # MinerU API PDF 全文解析 (批量上传 + 轮询)
│       ├── pdf_converter.py     # Markdown → PDF (pandoc + xelatex，备用路径)
│       └── email_sender.py      # SMTP 邮件发送 (TLS/SSL)
├── tools/                       # 辅助工具
│   ├── reset_pipeline.py        # 重置流水线状态（5 子命令 + --publisher 过滤）
│   ├── convert_md_to_pdf.py     # Markdown → PDF (pandoc + cloakbrowser 主路径)
│   ├── reset_empty_abstract.py  # 重置空摘要论文的 Phase D/E/G
│   ├── debug_llm_summary.py     # 诊断 LLM Summary JSON 解析失败
│   └── debug_publisher_urls.py  # 诊断 Publisher URL 抓取（headful 浏览器）
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
Phase A: RSS Feed 抓取
      │  发现论文 → 写入 DOI / 标题 / 链接
      ▼
Phase B: CrossRef 元数据
      │  补充作者 / 出版日期 / 期刊名 / 摘要
      ▼
Phase C: Publisher 页面 (cloakbrowser)
      │  爬取摘要 / PDF 链接 (绕过 Cloudflare)
      ▼
Phase D: 语义相似度初筛 (sentence-transformers)
      │  余弦相似度 → < 阈值则跳过 LLM (省 API 费)
      ▼
Phase E: LLM 相关性判断 (DeepSeek)
      │  → 判定相关/不相关 + 置信度 (并发)
      ▼
Phase E2: MinerU PDF 全文解析
      │  下载 PDF → MinerU API → 提取 Markdown 全文
      ▼
Phase F: LLM 论文总结 (DeepSeek)
      │  生成结构化总结 (优先用 MinerU 全文, 无全文则跳过)
      ▼
Phase G: 报告生成
      │  Markdown 格式输出 (仅含未报告的论文)
      ▼
Phase H: 邮件推送
        SMTP 发送报告给团队成员
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
- `semantic_similarity_score`

**LLM 相关性** (Phase E) — 五列：`llm_relevance_status` / `_error` / `_date`
- `llm_relevance_result` (0/1), `llm_relevance_confidence`, `llm_relevance_reason`

**MinerU 全文** (Phase E2) — 三列：`mineru_parse_status` / `_error` / `_date`
- `mineru_fulltext`, `mineru_output_dir`

**LLM 总结** (Phase F) — 三列：`llm_summary_status` / `_error` / `_date`
- `llm_summary_result` (JSON 字符串)

**报告状态** (Phase G) — 两列：`report_status` / `report_date`

**时间戳** (全局)
- `created_date`, `updated_date`

**状态值**：`FetchStatus` 枚举 (`pending` → `success` / `failed` / `skipped`)

# 关键设计决策

## 1. Phase D 作为 Phase E 的门禁

语义相似度初筛（sentence-transformers）成本极低（纯本地 CPU 推理），Phase E 的 LLM 调用按 token 计费。阈值 `SEMANTIC_SIMILARITY_THRESHOLD=0.3` 可调：
- `< 0.3` 直接标记 `llm_relevance_status = 'skipped'`，节省 API 费用
- `>= 0.3` 保留 `pending`，进入 Phase E 精细判断

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
- 用 `page.evaluate(fetch)` 在页面内请求 PDF（继承浏览器上下文）
- 下载后保存临时文件，MinerU 解析成功后移动到 `data/mineru_output/<doi>/paper.pdf`

**不依赖 response 监听** — 目前版本无需 `page.on("response")`，因为同域 fetch 足以覆盖所有 publisher。

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

支持两种格式：
1. **纯列表** → 自动拼接为 `domain_description`
2. **字典** — 包含 `domain_description`（段落描述）和 `keywords`（关键词列表）

`domain_description` 用于 Phase D（语义相似度）和 Phase E（LLM prompt），比纯关键词列表语义信息更丰富。

## .env

密钥存储文件（不提交到仓库），通过 `python-dotenv` 加载：

```ini
CROSSREF_MAILTO=your_email@example.com
MINERU_TOKEN=your_mineru_token_here
DEEPSEEK_API_KEY=sk-your-deepseek-key
```

`src/config.py` 通过 `os.getenv()` 读取，缺失时留空（对应功能跳过）。

# 阶段开关（SKIP_PHASE）

所有 9 个阶段可通过 `src/config.py` 中的 `SKIP_PHASE_A` ~ `SKIP_PHASE_H` 独立开关：

```python
SKIP_PHASE_A = True   # RSS 抓取
SKIP_PHASE_B = True   # CrossRef 元数据
SKIP_PHASE_C = True   # Publisher 页面
SKIP_PHASE_D = True   # 语义相似度
SKIP_PHASE_E = True   # LLM 相关性
SKIP_PHASE_E2 = True  # MinerU PDF 解析
SKIP_PHASE_F = False  # LLM 总结
SKIP_PHASE_G = False  # 报告生成
SKIP_PHASE_H = True   # 邮件推送
```

默认配置仅运行 Phase F + G（调试/开发模式），全量运行时全部设为 `False`。配套 `MAX_PAPERS_PER_PHASE` 控制每阶段处理上限（0 = 不限制）。

# 错误处理与韧性策略

## 1. 逐论文错误隔离

每个阶段用独立 `try/except` 包裹单篇论文的处理。一篇失败不影响同阶段其他论文，一阶段失败不影响后续阶段。

## 2. Phase C 重试机制

`phase_c_publisher()` 中对每篇论文最多尝试 3 次（`main.py:473-578`）：

| 尝试 | timeout | 冷却 | 条件 |
|------|---------|------|------|
| 第 1 次 | 5000ms | 0 | 首次加载 |
| 第 2 次 | 15000ms | 0 | 第 1 次失败 |
| 第 3 次 | 45000ms | 120-180s 随机 | 第 2 次失败 |

`NonResearchPageError` 不重试（非论文页面重试结果不变）。`consecutive_failures` 只在全部尝试都失败后递增。

## 3. LLM API 重试

两端 `call_deepseek_api()`（`paper_relevance.py` + `llm_summarize_deepseek.py`）均有 2 次重试 + 指数退避 `2^attempt s`。重试覆盖的异常类型：

- `requests.exceptions.RequestException` — 网络层失败
- `KeyError / IndexError / TypeError` — 响应结构异常
- `json.JSONDecodeError` — API 返回内容非法 JSON

## 4. JSON 反斜杠修复（双层防御）

LLM 输出的 JSON 字符串中 LaTeX 反斜杠未正确转义是常见问题。代码包含两层防御：

**第一层** — API 重试循环内（`call_deepseek_api`）：
```
API 返回 → json.loads() 验证 → 失败则 re.sub 修复 → 修复后重试 json.loads() → 仍失败则抛异常重试 API
```

**第二层** — Phase E/F 主线程（`main.py:792, 1055`）：
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

# 流水线子阶段详解

## Phase C — Publisher 页面抓取

使用 cloakbrowser 驱动 headful Chromium 和持久化 browser context：
- 同一 publisher 共用一个 session（`data/session_cached/<publisher>/`）
- cloakbrowser 自动处理浏览器指纹伪装，无需手动注入反检测 JS
- 页面间随机延迟 `PUBLISHER_PAGE_DELAY_MIN~MAX`（默认 3-5s），publisher 间冷却 15s
- 失败熔断：连续失败 `PUBLISHER_MAX_CONSECUTIVE_FAILURES`（默认 3）篇后自动中止，避免 IP 封禁
- Cloudflare 拦截检测：检查 HTML 中 `challenge-platform`、`_cf_chl_opt`、`cf-browser-verification` 关键词
- 按 publisher 分组处理，同一组复用浏览器实例（`SCRAPER_MAP` 管理 7 个 publisher）

7 个 Scraper 子类各适配不同的页面结构（meta 标签 / JSON-LD / XPath）。

## Phase E2 — PDF 下载策略

`BasePublisherScraper.download_pdf()` 处理 PDF 下载：

1. **建立上下文** — `goto(page_url)` 访问文章页，等待 Cloudflare Challenge 通过
2. **提取同域链接** — 扫描页面 `<a>PDF</a>` 按钮，用 `new URL(href, location.origin)` 提取同域 PDF URL（解决 APS 跨域问题）
3. **同域 fetch** — 在浏览器上下文中用 `page.evaluate(fetch(url))` 获取 PDF 字节流（继承 cookie/session）
4. **保存** — 写入临时文件 → MinerU 解析 → 移动到 `data/mineru_output/<doi>/paper.pdf`

**APS 跨域问题根因**：APS 使用双域名架构（`link.aps.org` 跳转、`journals.aps.org` 内容），`citation_pdf_url` 短链与文章页不同域。浏览器同源策略（SOP）拦截了跨域 `fetch`。从页面 DOM 中提取的同域路径不受此限制。

## Phase F — LLM 结构化总结

- 仅处理有 MinerU 全文的论文（无全文直接标记 skipped）
- 使用 `ThreadPoolExecutor` 并发调用 DeepSeek API
- 输出 JSON 包含 5 个字段：`one_sentence`、`motivation_and_goal`、`key_setup_and_method`、`main_results_and_physics`、`take_home_message`
- 可选后处理：`LLMFormulaFixer`（实验性，`SKIP_FORMULA_FIX = True` 默认关闭），用 flash 模型修复裸 LaTeX 命令的公式包裹

# PDF 转换路径

`tools/convert_md_to_pdf.py` 提供两种转换策略：

**主路径（推荐）**：pandoc → HTML → cloakbrowser → PDF
1. `pandoc --mathml --standalone` 生成含 MathML 的 HTML
2. cloakbrowser 加载 HTML，打印为 PDF
3. 不再依赖 texlive / xelatex，消除了 LaTeX 编译错误

**备用路径**：`src/utils/pdf_converter.py` 通过 pandoc + xelatex 转换
- 策略 A：自定义 LaTeX 模板（含 `xeCJK`、`Noto Sans CJK SC`、`\times` 兼容宏）
- 策略 B：无模板回退（适用于纯英文场景）
- 返回 `None` 表示失败（不抛异常）

# reset 工具族

`tools/reset_pipeline.py` 提供 5 个子命令，每个支持 `--publisher` 过滤：

| 命令 | 重置范围 | 典型用途 |
|------|---------|---------|
| `reset-semantic` | Phase D + E + G | 修改 domain_description / keywords 后 |
| `reset-publisher` | Phase C failed/skipped | 重试被 Cloudflare 拦截的论文 |
| `reset-mineru` | Phase E2 failed/skipped | 重试 PDF 解析失败的论文 |
| `reset-summary` | Phase F failed/skipped（`--all` 含 success） | 修改 prompt 后重新生成总结 |
| `reset-report` | Phase G reported | 重新汇入下次报告 |

关键设计：
- `reset-semantic` **不重置** MinerU 和 LLM Summary 结果（语义修改不影响已解析 PDF 和总结）
- `reset-publisher` **跳过** `NonResearchPageError` 条目（非论文页面重试无意义）
- 所有命令执行前打印 SQL + 行数，交互确认后才执行

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
