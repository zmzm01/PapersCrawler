> 此文档记录执行步骤、关键决策和经验教训。是精炼的上下文。

# 变更汇总

| 模块 | 变更 | 日期 |
|------|------|------|
| **测试修复** | `test_publisher_parse.py` 旧异常名 `NaturePageNotPaper` → `NonResearchPageError`（4 处） | 06-01 |
| **Email 检测** | 占位符判断从 `"your_" in username` 改为 `"@" not in username` | 06-01 |
| **代理配置** | Optica 硬编码代理 `http://127.0.0.1:10808` 移至 `config.py` 的 `PUBLISHER_PROXY` 字典 | 06-01 |
| **未使用变量** | `publisher.py` 中 `abstract_jsonld`、`keywords` 注释为 `#`（保留供参考） | 06-01 |
| **冗余删除** | `PaperRelevanceChecker.semantic_similarity()` 整个方法删除（`SemanticFilter` 才是正确实现） | 06-01 |
| **DB 查询加固** | `get_relevant_papers()` 增加 `AND llm_relevance_status = 'success'` 过滤 | 06-01 |
| **文档清理** | `doc-设计.md` 旧异常名 `NaturePageNotPaper` → `NonResearchPageError` | 06-01 |
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
| **调试工具** | 新增 `tools/debug_publisher_urls.py`  Publisher URL 诊断脚本 | 06-01 |
| **异常重命名** | `NaturePageNotPaper` → `NonResearchPageError`；修复 reset-publisher 误重试非论文页面 | 06-01 |

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

## 异常重命名：NaturePageNotPaper → NonResearchPageError

**动机**：原名带有 "Nature" 前缀，实际上 Science 的非论文页面也使用同一个异常，命名有歧义。

**解决**：
- `NaturePageNotPaper` → `NonResearchPageError`（`publisher.py` + `main.py` 共 11 处引用全部更新）
- 同时修复 bug：非论文页面被标记 `skipped` 时没有写入 error 信息，导致 `reset-publisher` 也会重置它们，造成无意义的重试
- `main.py` 中 `NonResearchPageError` 处理改用 `update_error_message()`，写入 `"NonResearchPageError: not a research article"`
- `tools/reset_pipeline.py` 中 `cmd_reset_publisher()` 的 WHERE 子句增加过滤：跳过 `publisher_page_fetched_error LIKE 'NonResearchPageError:%'` 的记录

## 类型标注修复

`call_deepseek_api()` 在两个文件中标注返回 `Dict[str, Any]`，实际返回 `str`（JSON 字符串）。两个文件均修正为 `-> str`。

## PDF 手动转换脚本

**动机**：Phase G 不再自动生成 PDF（pandoc/xelatex 系统依赖太重），但仍有转换需求。

**解决**：
- 新增 `tools/convert_md_to_pdf.py <input.md>`，调用 `pdf_converter.markdown_to_pdf()`
- `phase_g_report()` 末尾打印提示信息，引导用户使用此脚本

## Phase C fetch_page 重试机制

**动机**：部分出版商页面偶尔超时或被 Cloudflare 拦截，单次固定 5s 等待不够可靠。且问题具有随机性，两次重试都失败后重新运行代码却可能成功。

**解决**：`phase_c_publisher()` 内每篇论文的处理改为最多 3 次尝试：
- 第 1 次 `fetch_page(timeout=5000)`
- 第 2 次 `fetch_page(timeout=15000)`
- 第 3 次 `time.sleep(random.uniform(60, 180))` + `fetch_page(timeout=45000)`
- `NonResearchPageError` 不重试（非论文，重试结果不变）
- `consecutive_failures` 只在所有尝试都失败后递增

## Phase E2 PDF 下载重构

**动机**：Phase E2 PDF 下载原来在 `main.py` 中内联使用 Playwright（`sync_playwright()` + 反检测 JS 注入），与 publisher 爬虫的 Playwright → cloakbrowser 迁移不一致。

**解决**：
- `BasePublisherScraper` 新增实例方法 `download_pdf()`，将原来 `main.py` 中的 response 监听 + fetch 兜底逻辑搬入基类
- `phase_e2_mineru()` 改为：启动一个 `BasePublisherScraper`（session 专用目录 `data/session_cached/mineru_download/`）→ 逐篇调用 `download_pdf()` → 结束时 `close()`
- 项目内最后一个 `from playwright.sync_api import sync_playwright` 已删除，Playwright 完全移除
- 修复 bug：`download_pdf()` 中使用了 `logging` 但 `publisher.py` 未导入，导致 `NameError: name 'logging' is not defined`
- 修复 APS closed OA 论文 PDF 下载失败：`download_pdf()` 改为先访问 `page_url` 建立上下文，再用 `page.evaluate(fetch)` 请求 PDF，而非直接 `goto(pdf_url)`（直接访问会被 302 重定向）

## 各阶段开关补齐

**动机**：`config.py` 中只有 Phase C/E/E2/F/H 有 `SKIP_PHASE_*` 开关，Phase A/B/D/G 缺失，不利于调试。

**解决**：补齐全部 9 个阶段开关，并在各函数入口加守卫逻辑。

## reset-semantic 保留 MinerU 结果

**动机**：修改领域描述后，MinerU 解析结果不受影响，`reset-semantic` 不应清空已成功解析的 PDF 内容。

**解决**：从 `SEMANTIC_CASCADE` 中移除 MinerU 相关列（`mineru_parse_status`、`mineru_fulltext`、`mineru_output_dir` 等）。`reset-semantic` 后已解析论文保持 `mineru_parse_status='success'`，Phase E2 自动跳过；需重跑时使用 `reset-mineru` 单独控制。

## APS 跨域 PDF 下载修复（关键修改）

**问题分析**：APS 使用双域名架构——短链 `link.aps.org` 负责跳转，实际内容在 `journals.aps.org`。数据库中的 `pdf_url` 来自 `citation_pdf_url` meta 标签，格式为 `http://link.aps.org/pdf/...`。当 `download_pdf()` 先 `goto(page_url)` 到达 `journals.aps.org` 后，再 `evaluate(fetch(link.aps.org/pdf/...))` 时，**浏览器因跨域拦截了 `fetch` 请求**（同源策略/SOP，不是 CORS 问题）。这就是 9 篇全部失败的根因。

**关键发现**：页面上 PDF 按钮的 HTML 是 `<a href="/prl/pdf/...">PDF</a>`——这是一个**相对路径**，解析后与当前页面同域（`journals.aps.org`）。同域请求不受浏览器同源策略限制，`fetch` 可以正常获取 PDF。

**解决**：`download_pdf()` 中 `goto(page_url)` + `wait_for_timeout(5000)` 后，执行 `page.evaluate` 扫描页面上所有 `<a>` 标签，找到文本为 "PDF" 的链接，用 `new URL(href, location.origin)` 解析为同域绝对 URL，替换 DB 中的跨域短链。

**经验教训**：
- 不要假设 `citation_pdf_url` 与当前页面同域——它可能经过短链服务
- 从页面 HTML 中提取的链接（按钮/菜单）通常是同域的，比 meta 标签更可靠
- **浏览器同源策略**是跨域 `fetch` 失败的根本原因，比 CORS 更严格（CORS 至少会给响应头交互机会，SOP 直接拒绝）
- 其他 publisher（Nature/Science/Cambridge/AIP/IOP/Optica）的 `citation_pdf_url` 本就是同域，不受此问题影响

## LLM API 重试 + JSON 转义修复

**动机**：LLM Summary 和 Relevance 阶段偶发 API 失败且无重试；LLM 输出 JSON 中 LaTeX 反斜杠未正确转义，导致 `json.loads` 报 `Invalid \escape`。

**解决**：
- 两个 `call_deepseek_api()` 内层增加 `for attempt in range(2)` 重试，指数退避 `2^attempt s`
- `SUMMARIES_PROMPT` 加强反斜杠转义说明，增加正确/错误示例
- Phase E/F 的 `json.loads()` 前增加正则修复：`re.sub(r'\\(?![\\"/bfnrtu])', r'\\\\', result_str)`，将单反斜杠（非合法 JSON 转义）加倍

## reset-semantic 保留 LLM Summary 结果

**动机**：语义描述变更不影响已有的 LLM 总结结果，`reset-semantic` 不应清空已成功的总结。

**解决**：从 `SEMANTIC_CASCADE` 中删除 Phase F 4 行（`llm_summary_status`、`llm_summary_result` 等）。`reset-semantic` 后已有总结保持 `'success'`，Phase F 自动跳过。

## 空摘要修复

**动机**：Phase C 用空字符串覆盖了已有摘要（来自 Phase B），且成功判定只检查 title+doi+abstract 全空，未排除 abstract 单独为空的情况。

**解决**：
- `update_publisher_page()` SQL 中 `abstract` 改为 `CASE WHEN ? != '' THEN ? ELSE abstract END`，防止空摘要覆盖已有值
- 删除之前新增的空摘要检测（纠正/勘误类论文合法无摘要，Phase E 已有跳过逻辑）
- 新增 `tools/reset_empty_abstract.py`：将已入库的空摘要论文的 Phase D/E/G 重置为 pending，保留 MinerU 和 LLM 总结
- `call_deepseek_api()` 重试中增加 `json.JSONDecodeError` 捕获，防止 API 响应损坏时丢失重试机会

## LLM JSON 调试脚本

**动机**：Phase F 偶发 `Invalid \escape` 错误，正则修复未能覆盖，需定位 LLM 实际输出的内容。

**解决**：新增 `tools/debug_llm_summary.py <doi>`，读取指定论文的 MinerU 全文并调用 API，在 `json.loads` 失败时打印原始字符串（含错误位置上下文）、正则修复对比、激进的二次修复尝试。

## Inner JSON 验证移至 API 重试循环内

**动机**：`json.loads` 验证在 `call_deepseek_api` 返回之后才执行，API 重试循环不覆盖 JSON 非法的情况，导致重试无效。

**解决**：将 inner JSON 验证 + 正则修复移入 `call_deepseek_api()` 的重试循环内部：
- API 返回内容后立即验证 inner JSON，非法时尝试正则修复
- 修复后仍非法则抛异常，触发 API 重试
- 第二次重试后内容仍非法则走异常处理（成功率已大幅提高）

## 正则修复 `\(?` → `(?<!\\)\\(?`

**动机**：正则 `r'\\(?![\\"/bfnrtu])'` 缺少负向后顾，会错误地将正确转义 `\\` 中的第二个反斜杠也匹配并加倍，产生新的非法转义。

**解决**：改为 `r'(?<!\\)\\(?![\\"/bfnrtu])'`，只匹配**前面没有反斜杠**的反斜杠。

## Prompt 公式格式统一 + reset-summary --all

**动机**：旧 prompt 允许行内公式用 `\(` 或 `$` 二选一，导致不同总结中格式不统一，影响报告渲染。

**解决**：
- `SUMMARIES_PROMPT` 改为唯一指定：行内公式必须用 `\(...\)`，行间公式必须用 `\[...\]`
- `tools/reset_pipeline.py` `reset-summary` 子命令加 `--all` 参数，支持重置包括 `success` 在内的全部总结
- 所有子命令的 `-h` 详细列出受影响/不受影响的状态列

**重置并重新生成所有总结**：
```bash
python tools/reset_pipeline.py reset-summary --all
# 确认后，再运行主流水线（仅 Phase F 和 G 执行）
python src/main.py
```

## PDF 转换改为 HTML + cloakbrowser（公式待修复）

**动机**：pandoc → xelatex 路径对文本模式中的裸 LaTeX 命令（`\times`、`\mathrm` 等）过于脆弱，任何 `\(...\)` 范围外的 LaTeX 命令都导致编译崩溃。

**解决**：`tools/convert_md_to_pdf.py` 改为：
1. pandoc Markdown → HTML（`--mathml` 模式，MathML 由浏览器原生渲染）
2. cloakbrowser 无头打印 HTML → PDF
3. 不再依赖 xelatex / texlive

**当前状态**：可运行生成 PDF，但公式渲染暂不支持，PDF 中公式显示为空白。保留 `--mathjax` 升级路径（需解决 `file://` 协议下 CDN 加载问题或换用本地 MathJax）。

## LLM 公式格式修复

**动机**：Large Model 指令遵循不到位，部分 LaTeX 命令（`\times`、`\mathrm` 等）未用 `\(` 包裹。正则方案边缘 case 过多，总有遗漏。

**解决**：
- 新增 `LLMFormulaFixer` 类（`utils/llm_summarize_deepseek.py`），用 flash 模型修复裸 LaTeX 命令的公式包裹
- 新增 `LLMFormulaFixer` 类（`utils/llm_summarize_deepseek.py`），接收整个总结 dict 并用 json_object 模式修复
- 新增 `SKIP_FORMULA_FIX = True` 配置开关（**实验性功能**，默认关闭，需评估 prompt 效果后再开启）
- `phase_f_llm_summary()` 中条件初始化 + 条件调用 fixer，默认跳过

## 错误处理增强 + RSS 缓存简化

1. RSS 缓存改为每次覆盖，去除日期后缀
2. RSS 空解析结果增加 `logger.warning`
3. CrossRef 增加 429 请求过频特殊检测
4. Publisher Phase C 增加 CF 拦截时升级 cloakbrowser 提示 + `PageParseError` 时页面结构变更提示
5. DeepSeek API 调用增加状态码解析（401/402/429/503），映射为针对性错误信息
6. MinerU Token 过期自动检测（解码 JWT 的 `exp` 字段），30 天前 warning，7 天前 error

# 2026-06-02 — 测试体系重构：两套测试 + 零跳过

**背景**：测试中 5 个 `@pytest.mark.skip` 从不执行，形同虚设。2 个 RSS 测试依赖缓存文件，不存在时静默通过（假阴性）。`EmailSender.send()` 方法从未被测试。

**解决**：
1. 新增 `tests/fixtures/` — 存放真实响应快照（由 T3 脚本生成）
2. 新增 `tests/real/` — 3 个 T3 真实测试脚本（独立运行，无需 pytest）
   - `real_crossref.py` — 调用 CrossRef API，验证并保存 fixture
   - `real_llm_api.py` — 调用 DeepSeek API（相关性 + 总结），验证并保存 fixture
   - `real_email.py` — 发送真实测试邮件到配置地址
3. 改造 `test_rss.py` — 删 2 个文件依赖测试，新增内联 RSS XML 全流程测试
4. 改造 `test_crossref.py` — 3 个 `@skip` → mock `requests.Session.get`
5. 改造 `test_relevance.py` — 1 个 `@skip` → mock `requests.post`
6. 改造 `test_email.py` — 删 `@skip` + 无效 MIME 测试，新增 4 个 mock smtplib 测试
7. 清理 `conftest.py` — 删除不再使用的 markers（network/browser/slow）

**结果**：`pytest tests/` → 83 passed, 0 skipped（从 78 passed, 5 skipped 改进）

# 2026-06-02 — 代码重构：utils/ → processors/, db.py 迁移, main.py 拆分

**背景**：`src/utils/` 名不副实（装的是核心业务逻辑而非工具函数），`main.py` 单文件 1310 行，阶段函数耦合紧密，不利于 Web UI 按需调用。

**变更**：

1. `src/utils/db.py` → `src/db/database.py`
   - 数据库是基础设施，独立为 `src/db/` 包
   - 更新 3 处导入

2. `src/utils/` → `src/processors/`
   - 仅重命名目录，文件名不变
   - 更新 17 处导入（src/tests/tools 共 9 文件）

3. `main.py` (1310 行) → `src/pipeline/` (13 文件)
   - `pipeline/base.py` — 共享上下文（SCRAPER_MAP, create_scraper, logger）
   - `pipeline/phase_a.py ~ phase_h.py` — 每个阶段独立文件
   - `pipeline/runner.py` — 编排器，支持 `run_pipeline()` 全跑和 `run_phases()` 选择性跑
   - `main.py` → 简化到 10 行 CLI 包装

4. 新增 `tests/test_phases.py` — 验证各 phase 模块可导入，函数签名正确

**结果**：pytest 83 passed, 当前结构与 Web UI 兼容

# 2026-06-02 — Web UI 添加：FastAPI + SSE + 5 页面

**动机**：提供图形化界面替代 SKIP 开关来控制流水线阶段，查看数据库状态，灵活生成报告。

**实现**：
- 新增 `src/web/` 模块，基于 FastAPI + Jinja2
- 5 个页面：Dashboard（状态概览）、Pipeline（阶段控制 + 日志流）、Report（报告生成）、Logs（日志查看）、Config（配置展示）
- SSE (Server-Sent Events) 实时推送流水线日志到浏览器
- 子进程执行阶段（`POST /pipeline/run/{phase}`），互斥锁防并发
- 启动命令：`PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080`
- 无头服务器：`xvfb-run -a bash -c 'PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080'`
- `pipeline/runner.py` 新增 `__main__` 入口，支持 CLI `python src/pipeline/runner.py A B C`

**文件**：
- `src/web/__init__.py`, `src/web/app.py`
- `src/web/templates/{base,dashboard,pipeline,report,logs,config}.html`
- `src/web/static/css/style.css`, `src/web/static/js/app.js`

# 2026-06-03 — Phase C 加固：非论文检测 + 日志补齐 + CF 满3次重试 + APS 302兜底

**背景**：
1. Phase C 抓取 Erratum / Publisher's Note / Response to / Comment on 类非论文页面时，
   没有检测逻辑，标记为 success 并携带空 abstract 流入下游阶段。
2. Phase C 在成功/跳过/失败三个出口均无汇总日志，用户无法判断处理结果。
3. Cloudflare 拦截只尝试 2 次（第 0 次 continue → 第 1 次 raise），第 3 次（45s + 冷却 2min）从未到达。
4. APS `link.aps.org` 302 跳转到 `journals.aps.org` 时偶发 Playwright
   "navigation interrupted" 错误。

**变更**：

1. **非论文页面检测**（`pipeline/phase_c.py`）
   - 新增关键词表：`Erratum`, `Comment on`, `Response to`, `Publisher's Note`
   - 条件：`abstract` 为空 `AND` 标题含关键词 → 抛出 `NonResearchPageError`
   - 与 Nature/Science 的 `dc.type` 元数据检测互补，覆盖所有 publisher

2. **下游级联跳过**（`pipeline/phase_c.py`）
   - NonResearchPageError 被捕获后，除了设 `publisher_page_fetched_status = skipped`
   - 额外设 `semantic_filter_status = skipped` + `llm_relevance_status = skipped`
   - 防止 Phase D/E 继续处理非论文页面

3. **日志补齐**（`pipeline/phase_c.py`）
   - 成功出口：`logger.info("Publisher page OK: {doi}")`
   - 失败出口：`logger.warning("Phase C scrape failed after 3 attempts [{doi}]")`
   - CF 拦截日志增加 attempt 计数：`"Cloudflare detected (attempt 2/3)"`

4. **CF 重试机制**（`pipeline/phase_c.py`）
   - `if attempt == 0: continue` → `if attempt < 2: continue`
   - Cloudflare 拦截和全空页面现在都会跑满 3 次尝试（含 45s timeout + 2min 冷却）

5. **APS 302 导航兜底**（`sources/publisher.py`）
   - `fetch_page()` 中 `page.goto()` 包裹 try/except
   - 捕获 "navigation interrupted" 错误后，等待 3s，用跳转后的 URL 重试

6. **文档更新**（`docs/design.md`）
   - 新增「6. 非论文页面检测（NonResearchPageError）」节
   - 详述两级检测策略（Scraper 元数据 + 关键词兜底）
   - 非论文页 / 合法空摘要 / 全空页 三种情况的对比表

