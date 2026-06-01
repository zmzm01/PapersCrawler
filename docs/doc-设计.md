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
│   ├── conftest.py
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
│   │   ├── crossref.py          # CrossRef DOI 元数据查询
│   │   └── publisher.py         # 7 个出版社的 cloakbrowser 页面抓取器
│   └── utils/
│       ├── db.py                # SQLite 数据库 CRUD
│       ├── paper_relevance.py   # 语义过滤器 + LLM 相关性判断 (含 SemanticFilter / PaperRelevanceChecker)
│       ├── llm_summarize_deepseek.py  # DeepSeek API 论文总结
│       ├── paper_report_generator.py  # Markdown 报告生成
│       ├── mineru_paper_parser.py     # MinerU API PDF 全文解析
│       ├── pdf_converter.py     # Markdown → PDF (pandoc + xelatex，手动转换用)
│       └── email_sender.py      # SMTP 邮件发送
├── tools/                       # 辅助工具
│   ├── reset_pipeline.py        # 重置流水线状态（语义重判 / Publisher 重试等）
│   └── convert_md_to_pdf.py     # 手动将 MD 报告转换为 PDF
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

各模块特有的异常（如 `PageParseError`、`NaturePageNotPaper`、`NotFoundError`）保留在各自模块中。

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

单表 `papers`，每篇论文一行，按阶段添加字段。核心列按功能分组：

**基础信息** (Phase A)
- `doi` (TEXT PRIMARY KEY), `title`, `page_url`, `journal_name`, `publisher`, `paperdate_rss`

**CrossRef 元数据** (Phase B)
- `authors_json`, `paperdate_crossref`, `abstract` (可由 Phase B 或 Phase C 写入)
- `cr_metadata_fetched_status` / `_error` / `_date`

**Publisher 页面** (Phase C)
- `paperdate_page`, `pdf_url`
- `publisher_page_fetched_status` / `_error` / `_date`

**语义相似度** (Phase D)
- `semantic_similarity_score`
- `semantic_filter_status` / `_error` / `_date`

**LLM 相关性** (Phase E)
- `llm_relevance_result` (0/1), `llm_relevance_confidence`, `llm_relevance_reason`
- `llm_relevance_status` / `_error` / `_date`

**MinerU 全文** (Phase E2)
- `mineru_fulltext`, `mineru_output_dir`
- `mineru_parse_status` / `_error` / `_date`

**LLM 总结** (Phase F)
- `llm_summary_result` (JSON 字符串)
- `llm_summary_status` / `_error` / `_date`

**报告状态** (Phase G)
- `report_status` / `report_date`

**创建日期** (全局)
- `created_date`

状态值使用 `FetchStatus` 枚举: `pending` → `success` / `failed` / `skipped`

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

出版商 PDF 链接通常先返回 HTML 预览页，再由 JS viewer 异步加载真实 PDF：
- 主策略：`page.on("response")` 监听所有响应，捕获 Content-Type 为 `application/pdf` 的响应体
- 兜底：监听失败时用 `page.evaluate(fetch)` 在页面内重新获取（复用浏览器 session/cookie）
- 下载后先保存为临时文件，MinerU 解析成功后移动到 `data/mineru_output/<doi>/paper.pdf`

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
