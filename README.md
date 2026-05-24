# PapersCrawler — 文献自动追踪与推送

自动抓取领域核心期刊文章，筛选与组内工作相关的论文，生成结构化报告并推送。

## 项目结构

```
PapersCrawler/
├── configs/
│   ├── publishers.yaml          # 需要追踪的期刊配置 (RSS Feed + 出版社)
│   ├── keywords.yaml            # 研究领域关键词表 (自行填写)
│   ├── email.yaml               # SMTP 邮件推送配置
│   └── prompts/                 # LLM Prompt 模板目录 (预留)
├── data/
│   ├── papers.db                # SQLite 数据库 (自动生成)
│   ├── PaperCrawler.log         # 运行日志
│   ├── raw/
│   │   ├── rss/                 # RSS Feed XML 缓存
│   │   └── page/                # Publisher 页面 HTML 缓存 (调试用)
│   ├── reports/                 # 生成的 Markdown + PDF 报告
│   └── session_cached/          # Playwright 浏览器 Session 缓存
├── docs/                        # 数据源调研与 API 文档
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
│   ├── config.py                # 全局配置 (路径、API Key、Prompt)
│   ├── main.py                  # 主入口 — 8 阶段流水线
│   ├── sources/
│   │   ├── rss.py               # RSS Feed 抓取与解析
│   │   ├── crossref.py          # CrossRef DOI 元数据查询
│   │   └── publisher.py         # 7 个出版社的页面抓取器
│   ├── utils/
│   │   ├── db.py                # SQLite 数据库 CRUD
│   │   ├── paper_relevance.py   # 关键词匹配 + LLM 相关性判断
│   │   ├── llm_summarize_deepseek.py  # DeepSeek API 论文总结
│   │   ├── paper_report_generator.py  # Markdown / HTML 报告生成
│   │   ├── pdf_converter.py     # Markdown → PDF (pandoc + xelatex)
│   │   └── email_sender.py      # SMTP 邮件发送
│   └── test_for_rss_parse.py    # RSS 解析调试脚本
├── tools/                       # 辅助工具
│   └── reset_pipeline.py        # 重置流水线状态（语义重判 / Publisher 重试）
└── README.md
```

## 流水线架构

整个项目以 SQLite 数据库为中心，按 8 个阶段顺序执行。每个阶段读取上一阶段的输出，处理后写入数据库。

```
Phase A: RSS Feed 抓取
      │  发现论文 → 写入 DOI / 标题 / 链接
      ▼
Phase B: CrossRef 元数据
      │  补充作者 / 出版日期 / 期刊名
      ▼
Phase C: Publisher 页面
      │  爬取摘要 / PDF 链接 (Playwright 浏览器)
      ▼
Phase D: 语义相似度初筛
      │  sentence-transformers → 余弦相似度 → <0.3 则跳过 LLM
      ▼
Phase E: LLM 相关性判断
      │  DeepSeek API → 判定相关/不相关 + 置信度
      ▼
Phase E2: MinerU PDF 全文解析
      │  下载 PDF → MinerU API → 提取 Markdown 全文
      ▼
Phase F: LLM 论文总结
      │  生成结构化总结 (优先用全文, 回退到摘要)
      ▼
Phase G: 报告生成
      │  Markdown + PDF 双格式输出
      ▼
Phase H: 邮件推送
        SMTP 发送报告给团队成员
```

## 快速开始

### 1. 安装依赖

```bash
pip install requests feedparser beautifulsoup4 parsel playwright pyyaml python-dateutil
pip install sentence-transformers  # 语义相似度初筛
pip install pytest  # 测试
playwright install chromium  # 安装 Chromium 浏览器
```

### 2. 配置

**configs/keywords.yaml** — 填写你的研究领域关键词：

```yaml
- laser plasma
- wakefield acceleration
- proton acceleration
- inertial confinement fusion
- ultrafast optics
```

**configs/email.yaml** — 填写邮件发送信息（可选，不填则跳过推送）：

```yaml
smtp_host: "smtp.qq.com"
smtp_port: 587
use_tls: true
username: "your_email@qq.com" # 邮箱账号
password: "your_auth_code" # 授权码（不是邮箱密码！）
from_addr: "your_email@qq.com"
to_addrs:
  - "colleague1@example.com"
  - "colleague2@example.com"
```

**src/config.py** — 填写 API Key：

```python
CROSSREF_MAILTO = "your_email@example.com"  # CrossRef API 礼貌要求
LLM_API_CONFIG_DICT = {
    "api_key": "sk-your-deepseek-key",      # DeepSeek API Key
    ...
}
```

### 3. 运行

```bash
# 桌面环境
python src/main.py

# 无图形界面服务器 (运行 Publisher 抓取阶段)
xvfb-run -a python src/main.py
```

### 4. 运行测试

```bash
# 运行所有离线测试
pytest tests/ -v

# 跳过 PDF 测试 (需要 pandoc)
pytest tests/ -v -k "not pdf"

# 仅运行数据库测试
pytest tests/test_db.py -v
```

### 5. 重置流水线状态

```bash
# 更新 domain_description / 关键词后，重置语义判断 + 下游全部结果
python tools/reset_pipeline.py reset-semantic

# 仅重置 APS 论文的语义判断
python tools/reset_pipeline.py reset-semantic --publisher aps

# 重置 Publisher 页面抓取失败的论文（触发 Phase C 重试）
python tools/reset_pipeline.py reset-publisher

# 仅重试 APS 的失败抓取
python tools/reset_pipeline.py reset-publisher --publisher aps

# 重置 MinerU PDF 解析失败的论文（触发 Phase E2 重试）
python tools/reset_pipeline.py reset-mineru

# 仅重试 APS 的 MinerU 失败解析
python tools/reset_pipeline.py reset-mineru --publisher aps

# 重置 LLM 总结失败的论文（触发 Phase F 重试）
python tools/reset_pipeline.py reset-summary

# 重置报告状态，使已报告论文重新出现在下次报告中
python tools/reset_pipeline.py reset-report
```

脚本执行前会打印 SQL 和影响行数，需要手动确认 `y` 才执行。

## 支持的出版社/期刊

| 出版社    | 期刊数                                              | 爬虫类             |
| --------- | --------------------------------------------------- | ------------------ |
| Nature    | 4 (Nature, Nature Physics/Photonics/Communications) | `NatureScraper`    |
| Science   | 2 (Science, Science Advances)                       | `ScienceScraper`   |
| APS       | 7 (PRL ×2, PRAB ×2, PRE, PRApplied ×2)              | `APSScraper`       |
| Cambridge | 1 (HPLSE)                                           | `CambridgeScraper` |
| AIP       | 5 (PoP ×2, APL ×2, RSI)                             | `AIPScraper`       |
| IOP       | 1 (PPCF)                                            | `IOPScraper`       |
| Optica    | 2 (Optica, Optics Express)                          | `OpticaScraper`    |

## Publisher 爬虫策略

参见 `src/sources/publisher.py` 中的详细注释。核心原则：

1. **Persistent Context** — 同一个 publisher 共用一个浏览器 session
2. **Headful Chromium** — 不使无头模式（Cloudflare 检测 headless）
3. **固定浏览器指纹** — UA / viewport / locale 固定不变
4. **真人节奏** — 页面间隔 2~30 秒随机延迟
5. **复用 Page** — 不频繁 new_page()
6. **校园网** — IP Reputation 是 anti-bot 最关键的因素

## 数据源优先级

```
RSS → DOI (发现)
   ↓
CrossRef API → metadata (补充)
   ↓
Publisher Page → abstract (补充非 OA 论文摘要)
```

## 待办事项

- [x] RSS 抓取模块
- [x] CrossRef 元数据抓取模块
- [x] Publisher Scraper 模块
- [x] 关键词筛选相关文献
- [x] LLM 精细判断相关性
- [x] LLM 论文结构化总结
- [x] 报告模板制作 (Markdown + PDF)
- [x] SMTP 分发
- [x] 日志模块
- [x] 分模块测试
- [x] MinerU PDF 解析整合到流水线
- [x] 语义相似度方法判断相关性 (sentence-transformers)
- [ ] 热点/趋势分析
- [ ] 并发升级 + 数据库同步升级

## Changelog

### 2026-05 — Pipeline 全面修复与增强

**Phase A — RSS Fetch**
- 删除无用的 `rss_fetched_status` / `rss_fetched_date` DB 列（写入后从未被任何查询读取）

**Phase B — CrossRef**
- `parse_work()` 作者为空时返回 `None` 而非 `[]`，避免空列表被误判为成功
- `phase_b_crossref()` 检测作者缺失时标记 `failed` 而非 `success`
- 新增 CrossRef abstract 存储：`update_crossref_metadata()` 增加 `abstract` 参数，空值不覆盖 Phase C 已写入的摘要（`CASE WHEN`）

**Phase C — Publisher Scraper**
- Nature `datePublished` 标准化：ISO 8601 (`2026-05-19T00:00:00Z`) → `YYYY-MM-DD`
- CF 拦截检测：从 `abstract+pdf_url` 双空改为 `title+doi+abstract` 三空检测；增加 CF 指纹关键词 (`challenge-platform`, `_cf_chl_opt`, `cf-browser-verification`)
- 页面间随机延迟 `5~20s` + publisher 间冷却 `15s`，避免 IP 信誉受损
- 同 publisher 连续失败 `PUBLISHER_MAX_CONSECUTIVE_FAILURES` 篇后自动中止
- Nature/Science scraper `dc.type` 逻辑修复：空值时正确抛 `PageParseError` 而非静默跳过
- NatureScraper JSON-LD 解析包裹 `try/except` 保护
- OpticaScraper 双赋值清理
- 浏览器指纹增强：`hardwareConcurrency`=8, `deviceMemory`=8, `maxTouchPoints`=0, viewport=1920x1080

**Phase D — Semantic Filter**
- 新增 `semantic_filter_error` DB 列（修复崩溃级 bug）
- 关键词列表 → 段落级 `domain_description` 自然语言描述，sentence-transformers 语义信息更丰富
- 删除废弃的 `keywords_filtered_*` DB 列和 `update_keyword_filter()` 方法

**Phase E — LLM Relevance**
- `PaperRelevanceChecker` 支持 `domain_description` 参数，LLM prompt 同时包含段落描述和关键词列表
- `load_keywords()` 返回 `{"keywords": [...], "domain_description": "..."}` dict

**Phase E2 — MinerU PDF**
- PDF 下载：`requests.get()` → Playwright 浏览器（复用反检测策略和 session cookie）
- MinerU 输出持久化到 `data/mineru_output/`，PDF 副本也保存到同一目录 `paper.pdf`
- DB 新增 `mineru_output_dir` 列存储相对路径
- Playwright 初始化移入 `try` 块，`finally` 增加 None 检查

**Phase F — LLM Summary**
- 无 MinerU 全文的论文直接跳过，不回退到标题+摘要
- 新增 `json.JSONDecodeError` 专用异常处理
- `LLMContextLenghExceed` → `LLMContextLengthExceed`（拼写修正）
- `LLMAPICallError` / `LLMResponseParseError` 统一从 `paper_relevance` 导入

**Phase G — Report**
- 新增 `report_status` / `report_date` DB 列，报告过的论文不再重复出现
- `get_papers_with_summary()` → `get_papers_for_report()` （仅拉取未报告的新论文）
- 报告中新增原文摘要展示
- 删除 PDF 生成（pandoc/xelatex 依赖过重），仅保留 Markdown

**Phase H — Email**
- 仅附加 `.md` 文件，正文保持纯文本
- `load_email_config()` 包裹 `try/except` 保护
- SMTP 连接 `try/finally` 保证 `quit()` 执行

**Config**
- `keywords.yaml` 支持 `domain_description` 段落和 `keywords` 双字段
- 新增 `PUBLISHER_PAGE_DELAY_MIN/MAX`, `PUBLISHER_MAX_CONSECUTIVE_FAILURES` 配置

**DB Schema**
- 删除：`rss_fetched_status`, `rss_fetched_date`, `keywords_filtered_status`, `keywords_filtered_matched_num`, `keywords_filtered_date`
- 新增：`semantic_filter_error`, `report_status`, `report_date`
- 新增方法：`get_papers_for_report()`, `mark_papers_reported()`
- 删除方法：`update_keyword_filter()`

### 2026-05-24 — 性能优化与工具链完善

**Phase E — LLM 相关性判断**
- 并发化：串行 `for` → `ThreadPoolExecutor`（并发上限 `LLM_CONCURRENT_MAX=20`）— N 篇论文总耗时从 `Σ(slow)` 降为 `max(slow)`
- 无摘要论文不再提交 LLM，标记 `llm_relevance_status = 'skipped'` 跳过

**Phase E2 — MinerU PDF 下载修复**
- PDF 下载：`page.on("response")` 监听所有网络响应捕获 PDF（解决出版商 PDF viewer 页面导致 response.body() 返回 HTML 的问题）
- 兜底：监听失败时用 `page.evaluate(fetch)` 重新获取
- PDF 保存到 MinerU 输出目录 `paper.pdf`（不再删除）
- DB 新增 `mineru_output_dir` 列存储相对路径

**Phase F — LLM 总结**
- 并发化：同 Phase E 使用 `ThreadPoolExecutor`

**LLM API 诊断**
- `call_deepseek_api()` 增加请求计时日志（输入/输出字符数 + 耗时），便于定位 API 性能瓶颈
- `MinerU _poll_batch()` 错误信息增加 `err_code`，根据 MinerU API 错误码表辅助排查

**工具链**
- 新增 `tools/reset_pipeline.py`，支持 5 个子命令：
  - `reset-semantic` — 重置语义判断及下游全部状态
  - `reset-publisher` — 重置 Publisher 抓取（`failed` + `skipped`）
  - `reset-mineru` — 重置 MinerU 解析（`failed` + `skipped`）
  - `reset-summary` — 重置 LLM 总结（`failed` + `skipped`）
  - `reset-report` — 重置报告状态（重新汇入报告）
- 所有命令支持 `--publisher` 过滤，执行前交互确认

**DB Schema**
- 新增：`mineru_output_dir`
