> 此文档记录执行步骤、关键决策和经验教训。是精炼的上下文。

# 变更汇总

| 模块 | 变更 | 日期 |
|------|------|------|
| Phase A | 删除未使用的 `rss_fetched_status` / `rss_fetched_date` 列 | 05-23 |
| Phase B | 作者为空时标记 failed 而非 success；增加 abstract 存储（CASE WHEN 不覆盖已有值） | 05-23 |
| Phase C | CF 拦截检测增强、随机延迟 + 失败熔断、浏览器指纹加固、Nature JSON-LD try/except | 05-23 |
| Phase D | 新增 `semantic_filter_error` 列；关键词列表 → `domain_description` 段落语义 | 05-23 |
| Phase E | 支持 `domain_description`；并发化 ThreadPoolExecutor；无摘要论文跳过 LLM | 05-23/24 |
| Phase E2 | Playwright 下载 PDF（response 监听 + fetch 兜底）；输出持久化；DB 新增 `mineru_output_dir` | 05-23/24 |
| Phase F | 无全文直接跳过不回退；并发化；异常类型细化；拼写修正 | 05-23/24 |
| Phase G | 新增 `report_status` / `report_date`；仅报告新论文；删除 PDF 生成 | 05-23 |
| Phase H | try/except 保护；try/finally 确保 quit()；仅附加 .md | 05-23 |
| Config | keywords.yaml 支持双字段；新增爬虫延迟/熔断配置；`LLM_CONCURRENT_MAX` | 05-23/24 |
| DB Schema | 删除 5 列、新增 3 列、新增/删除若干方法 | 05-23/24 |
| 工具链 | `tools/reset_pipeline.py` 支持 5 子命令 + --publisher 过滤 | 05-24 |
| **新增** `src/common.py` | 共享 `Paper` dataclass + 4 个 LLM 异常；去重、消除循环导入 | 06-01 |
| **密钥重构** | 硬编码密钥 → `.env` + `python-dotenv` 加载 | 06-01 |
| **Phase C** | Playwright → cloakbrowser；删除反检测 JS 注入 | 06-01 |
| **Phase A** | `parse_rss()` 返回 `Paper` 对象而非 dict（数据模型统一） | 06-01 |
| **异常异常去重** | `LLMConfigurationError` 去重；类型标注修复 | 06-01 |
| **__main__ 安全** | 3 个文件的测试代码中硬编码密钥替换为 `os.getenv` 占位符 | 06-01 |
| **PDF 转换** | 新增 `tools/convert_md_to_pdf.py` 手动转换脚本 | 06-01 |

# 2026-05-23 — Pipeline 全面修复与增强

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

# 2026-05-24 — 性能优化与工具链完善

**Phase E — LLM 相关性判断**
- 并发化：串行 `for` → `ThreadPoolExecutor`（并发上限 `LLM_CONCURRENT_MAX=20`）— N 篇论文总耗时从 `Σ(slow)` 降为 `max(slow)`
- 无摘要论文不再提交 LLM，标记 `llm_relevance_status = 'skipped'` 跳过

**Phase E2 — MinerU PDF 下载修复**
- PDF 下载：`page.on("response")` 监听所有网络响应捕获 PDF（解决出版商 PDF viewer 页面导致 response.body() 返回 HTML 的问题）
  - 策略说明：出版商 PDF 链接通常先返回 HTML 预览页，由 JS viewer 异步加载真实 PDF。仅靠 `page.goto()` 的 response 获取不到真实 PDF 内容。
- 兜底：监听失败时用 `page.evaluate(fetch)` 在页面内重新获取（复用浏览器 session/cookie）
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
- 设计考量：不提供一键重置全部，防止误操作丢失数据

**DB Schema**
- 新增：`mineru_output_dir`

# 2026-06-01 — 代码重构：共享模型、密钥重构、cloakbrowser

## 新增 `src/common.py` — 共享数据模型 + 异常

**动机**：`Paper` dataclass 原本定义在 `publisher.py`，RSS 要用它就必须从 publisher 导入，造成不合理的依赖。LLM 异常在 `paper_relevance.py` 和 `llm_summarize_deepseek.py` 中重复定义，互相导入混乱。

**解决**：新建 `src/common.py`，存放所有跨模块共享的类型：

```
src/common.py
├── Paper dataclass          ← RSS + Publisher 统一返回类型
├── LLMConfigurationError    ← 从 paper_relevance 迁入，去重
├── LLMAPICallError          ← 从 paper_relevance 迁入
├── LLMResponseParseError    ← 从 paper_relevance 迁入
└── LLMContextLengthExceed   ← 从 llm_summarize_deepseek 迁入
```

各模块特有的异常（`PageParseError`、`NaturePageNotPaper`、`NotFoundError` 等）保留在各自模块中。

## 密钥存储：硬编码 → `.env`

**动机**：4 个密钥（CROSSREF_MAILTO、MINERU_TOKEN、DEEPSEEK_API_KEY × 2）硬编码在 `config.py` 中，有泄露风险。

**解决**：
- 新建 `.env.example`（含占位符，提交到仓库）
- `.env` 由用户自行填写，已加入 `.gitignore`
- `src/config.py` 使用 `python-dotenv` + `os.getenv()` 加载
- 3 个文件的 `__main__` 测试代码中的硬编码密钥也替换为 `os.getenv` 占位符

## Publisher 爬虫：Playwright → cloakbrowser

**动机**：Playwright + 手动反检测 JS 注入仍无法可靠绕过 Cloudflare。

**解决**：
- `BasePublisherScraper.start_browser()` 改为使用 `cloakbrowser.launch_persistent_context()`
- 删除整段反检测 JS 注入（20 行 `page.evaluate`），cloakbrowser 内部处理
- 删除 `self.pw = sync_playwright().start()` / `self.pw.stop()` 配套代码
- 7 个子类（`APSScraper` ~ `OpticaScraper`）零修改

## 数据模型统一：RSS 返回 `Paper`

**动机**：RSS `parse_rss()` 返回 `list[dict]` 而 Publisher 返回 `Paper` dataclass，格式不一致。

**解决**：
- `rss.py` 导入 `Paper` 对象，`parse_rss()` 改为返回 `list[Paper]`
- dict 中的 `link` → `url`，`updated` → `date`
- `main.py` `phase_a_rss()` 中的 dict 访问（`paper["doi"]`）改为属性访问（`paper.doi`）

## 类型标注修复

`call_deepseek_api()` 在两个文件中标注返回 `Dict[str, Any]`，实际返回 `str`（JSON 字符串）。两个文件均修正为 `-> str`。

## PDF 手动转换脚本

**动机**：Phase G 不再自动生成 PDF（pandoc/xelatex 系统依赖太重），但仍有转换需求。

**解决**：
- 新增 `tools/convert_md_to_pdf.py <input.md>`，调用 `pdf_converter.markdown_to_pdf()`
- `phase_g_report()` 末尾打印提示信息，引导用户使用此脚本

# 遗留问题 / 待办

- **热点/趋势分析** — 基于历史论文数据，统计关键词频率变化、新兴研究方向发现
- **并发升级** — 当前 Phase E/F 使用 ThreadPoolExecutor，但 DB 写入仍是串行瓶颈。考虑异步架构（asyncio + aiosqlite）
- **无摘要兜底** — Phase E 对无摘要论文标记 skipped，将来可尝试用 OCR/title-only 轻度判断
- **配置热加载** — 目前配置在 `main()` 入口一次性加载，修改后需重启
