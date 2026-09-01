# 当前任务与决策记录

> 本文只保留近期进展、当前决策和未决事项。完整历史流水账已归档至 [`docs/archive/tasks-legacy.md`](archive/tasks-legacy.md)。

## 2026-09-01：来源站点访问策略与 Optica E2 路由统一

- 配置根键由 `publisher` 更名为 `source_access`，明确其描述的是访问论文来源站点的策略，而非仅 Phase C；保留旧键读取兼容并在使用时输出迁移警告。
- `source_access.routes.<source>` 定义来源专属主路由。Phase C 与 E2 延迟解析文章页、下载 PDF 时共用，Optica 因中国地区出口信誉较低而配置的代理不再被 E2 忽略。
- `source_access.fallback_proxy_url` 保持为仅供 Phase C 常规重试耗尽后的末级代理，不与来源专属主路由混淆。

## 2026-08-31：Cloudflare Pages Token 统一使用 `.env`

- 按项目既有密钥管理方式，部署所需的 `CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_API_TOKEN` 和
  `CLOUDFLARE_PAGES_PROJECT` 统一由根目录 gitignored 的 `.env` 管理，不再维护单独 YAML 配置文件。
- 部署脚本显式从项目根 `.env` 加载这三个值，日常命令无需手动 export；CI 可直接注入同名变量。

## 2026-08-31：统一错误记录与跨日通知修复

- 新增 `common.format_error_for_record()`，各论文阶段将错误以 `异常类名: 消息` 的稳定格式写入
  既有 error 列（最长 500 字符）；避免 LLM API、响应解析、上下文超限和未知异常在 Dashboard
  中只剩模糊文本。Phase C 的无 page URL 也改为写入 `MissingPageURL`，不再只有 failed 状态。
- 未知的 CrossRef、OpenAlex、E/F 和 FormulaFixer 异常记录 traceback；损坏的 settings、prompt、
  publisher、keywords 配置会记录文件路径和 traceback，而不再静默退化。
- ntfy 阶段识别修复了 `E`，并遍历开始日至结束日之间的全部日志文件，保证跨午夜运行的告警可见。
- WebUI middleware 对未处理请求异常记录 method/path 与 traceback，只向客户端返回通用 500，避免
  内部细节泄漏。

## 2026-08-30：OpenAlex 元数据 fallback 与全文候选解析

- B 阶段形成 CrossRef → OpenAlex → Publisher 的字段级链路：CrossRef 非空字段优先，OpenAlex
  仅补缺失字段并重建 `abstract_inverted_index`；记录独立状态与字段来源。
- CrossRef `link` 和 OpenAlex 外部 OA locations 写入 `paper_fulltext_locations`，默认不下载
  `content.openalex.org`。E2 依来源优先级依次尝试候选地址，保留旧 `papers.pdf_url` 兼容。
- 验收补强：CrossRef 缺作者时也保存其余非空字段并调用 OpenAlex；任何关键字段缺失都会触发
  字段级补全，空字段不会擦除 RSS 现有值；OpenAlex 网络请求按配置并发、DB 合并串行。
  下载/解析重试成功会清除旧错误。Accepted Paper 即使在重定向后才识别，也标记为 skipped
  并释放当日配额。
- E2 PDF 浏览器强制不配置 Publisher 代理；requests Session 设置 `trust_env=False`。文章页
  导航失败不阻断 PDF 尝试，Accepted Paper URL 不进入下载配额。

## 2026-08-30：人工审核覆盖总结与报告筛选

- 报告、报告预览和 Dashboard 的 reportable 统计统一使用有效相关性分类：无人工审核时采用 E3
  分类，有最新人工审核时以人工 A/B/C/D/uncertain 为准；人工 C/D/uncertain 不再因已有 Summary
  成功而进入报告，人工 A/B 可使原本 C/D 的论文进入后续总结和报告。
- Phase F 待总结队列同步使用有效分类，避免无效论文继续消耗总结配额；报告快照展示人工分类，
  非空人工备注优先作为判断理由。
- WebUI 相关性审核队列新增 Summary 时间（新到旧）排序，未生成 Summary 的记录排在最后；补充
  数据库、预览、报告快照和审核队列回归测试。

## 当前状态（2026-08-26）

- 核心流水线为 A-RSS/A-CR → B → C → E → E2 → E3 → F → G → H。
- 推荐运行入口为 `tools/run_pipeline.py`；旧入口仅兼容保留。
- WebUI 当前提供 Dashboard、Papers、Report 和 Relevance Review。
- WebUI 推荐由 systemd 用户级服务常驻管理；日常/每周流水线继续由 cron 调度。
- E3 正文终审是报告硬门槛：必须 `fulltext`、有效 A/B 且 F 总结成功；有人工审核时以最新人工分类为准。
- 自动运行结束最多发送一条 ntfy 汇总，详细错误写本地日志。

## 2026-08-29：通用 CrossRef 摘要短路与 Publisher Bot 阻断隔离

- Phase C 不再把“Publisher 页面成功”作为标题/摘要相关性初筛的前置条件。新增
  `publisher.skip_if_crossref_abstract`（默认 `true`）：只要 B 阶段已有有效 CrossRef 摘要，
  所有 Publisher 默认跳过浏览器抓取；E2 在确实需要 PDF 且缺少 `pdf_url` 时再延迟访问页面。
  Scraper 类保留类属性覆写能力，特殊站点可声明必须访问页面。
- 为避免 Radware Bot Manager、验证码等页面每天被完整重试，`papers` 新增
  `publisher_page_retry_count`、`publisher_page_retry_after`、`publisher_page_failure_kind`。
  Phase C 检测到 Bot 阻断时记录 `bot_block`、递增次数并写入冷却时间；daily 自动重置只处理
  冷却结束且未达 `publisher.bot_max_retries` 的记录，达到上限后隔离。迁移前错误文本含
  `bot block` 的历史记录同样按隔离处理。
- `tools/run_pipeline.py` 新增 `--retry-bot-blocks`，用于人工绕过冷却/隔离并让 Bot 阻断论文
  绕过摘要短路强制重试；普通
  `--reset-publisher` 保留对非 Bot 失败的自动重试。
- 新增数据库、Phase C 和 CLI 回归测试，验证通用摘要短路、Bot 状态迁移/冷却/隔离及强制重试。

## 2026-08-29：隔离测试日志

- 新增 `PAPERSCRAWLER_LOG_DIR` 日志目录覆盖项，所有 CLI、兼容入口和 WebUI 均遵循该设置。
- pytest 在收集测试模块前将该变量指向临时目录；通过子进程启动 CLI 的测试不再把模拟错误、dry-run
  和测试夹具写入 `data/logs/`。

## 2026-08-29：Command Code LLM endpoint 与模型 ID 配置

- LLM endpoint 和 API Key 改为优先从 `.env` 的 `LLM_BASE_URL`、`LLM_API_KEY` 读取；`LLM_BASE_URL` 可以是 `/v1` 基础地址，也可以是完整的 `/chat/completions` endpoint。
- 新增 `LLM_MODEL_LIST` 作为可选模型目录 endpoint；流水线不在启动时强制请求模型目录，避免目录服务故障阻塞抓取和总结。
- 根据 Command Code `/models` 返回的精确 ID 更新当前角色：Phase E 使用 `Qwen/Qwen3.7-Flash`，Phase E3 使用 `claude-sonnet-5`，Phase F 使用 `MiniMaxAI/MiniMax-M3`，FormulaFixer 使用 `Qwen/Qwen3.7-Flash`。
- 按调用量和任务难度重新分层：高频的 E/FormulaFixer 关闭思考并使用低成本 Flash 模型；E3 正文终审使用更强的 Sonnet 5 并保留思考；F 总结继续使用支持长上下文、中文结构化输出且成本可控的 MiniMax M3。
- 保留 `DEEPSEEK_API_KEY` 作为未设置 `LLM_API_KEY` 时的兼容回退；旧的 YAML `llm.base_url` 只作为环境变量缺失时的回退。

## 2026-08-29：静态 KaTeX 公式校验与 Prince PDF 导出

- 新增 Node 渲染器 `report-site/scripts/render-markdown-katex.mjs`：先保护 Markdown 中的
  `\(...\)` / `\[...\]` 公式，再用 `marked` 生成 HTML，以 KaTeX 严格模式替换为静态 HTML/MathML，
  并复制本地 CSS/字体；转换时不依赖 Chrome 或 CDN。
- 新增 `tools/convert_md_to_pdf.py` 与 `md_to_pdf_prince.py`：静态 HTML 交给 Prince 生成 PDF；
  免费版的右上角水印作为可接受限制。缺少 Node、npm 依赖或 Prince 时安全失败，不伪造输出。
- FormulaFixer 复用该渲染器的 `--validate` 结构化错误：把无法渲染的公式和 KaTeX 诊断发送给 LLM，
  并要求修复后再次通过验证；验证器不可用时降级为既有修复行为。允许保留 KaTeX 支持的复杂环境。
- `formula_fix.max_repair_rounds` 将“校验 → LLM → 验收”作为一个不可拆分的 round 配置，默认 1；
  若验收仍失败，下一轮将新的报错和上轮输出交给 LLM，达到上限仍失败则回退原文本。

## 2026-08-28：修复错误快照生命周期与本地 PDF 导入提交

- 错误快照优先使用已缓存的 HTML；当 Phase C 在关闭 fallback 浏览器后执行诊断保存时，不再访问已关闭的 Playwright page，避免 `Event loop is closed` 二次警告遮蔽原始导航错误。
- `import_local_pdf.py` 的 UPDATE 现在显式提交事务。此前命令可以正确复制 PDF 并打印 `影响行数=1`，但连接关闭前未提交会使数据库状态回滚为原值；新增端到端临时数据库回归测试覆盖复制和状态持久化。

## 2026-08-28：ntfy 通知切换为 Web App 阅读版

- **背景**：此前为 Android 通知栏设计的紧凑故障摘要可节省空间，但几乎没有可读性；当前主要通过 ntfy Web App 查看通知。
- **布局**：恢复 E 初筛、E3 正文终审和 F 总结的完整状态/分类统计；通知按“运行概览 → 阶段执行 → 相关性判断 → 总结 → 问题与错误 → 连续失败提醒”分区。
- **Markdown**：使用 ntfy Web App 支持的标题、粗体、斜体、列表、引用块、行内代码和分隔线；继续不使用表格、HTML、`<details>` 和 Dashboard 链接。
- **边界**：保留单条最终通知、错误脱敏、3500 UTF-8 bytes 上限和通知失败不影响流水线；Android/不支持 Markdown 的客户端不作为主要排版目标。

## 2026-08-26：WebUI systemd 部署模板

- 新增 `deploy/systemd/paperscrawler-web.service`，用于用户级 systemd 管理 WebUI。
- 默认绑定 `127.0.0.1:8080`、单 worker、`INFO` 日志，并在异常退出后自动重启；日志同时保留在
  `data/logs/` 和 journald。
- 明确 WebUI 与流水线职责分离：WebUI 不需要 `xvfb-run`，无头服务器的 Xvfb 仅用于 Phase C。
- 同步更新 `README.md`、`docs/usage.md` 和 `docs/design.md`；流水线 cron 行为不变。

## 2026-08-26：修复 Publisher 早期导航失败时的错误快照回归

- `BasePublisherScraper` 在构造时初始化 `html`，并在错误快照保存时使用安全兜底，避免 `page.goto()` 尚未成功就触发 `'OpticaScraper' object has no attribute 'html'`，从而遮蔽真正的导航异常。
- 新增离线回归测试，覆盖导航在页面内容捕获前失败、原始 `PageParseError` 保留以及错误 HTML 快照成功写入。
- 该问题源自 2026-08-01 的错误快照实现调整；Optica 当晚的 `ERR_ABORTED at chrome-error://chromewebdata/` 仍是独立的实际抓取失败，修复只保证诊断链路不再二次失败。

## 2026-08-24：建立独立 Astro 报告站点（与 Hugo 并行）

- 新增 `report-site/`，独立展示 PapersCrawler 报告，不依赖 `../MySite`，使用报告卡片、论文目录、A/B 等级、折叠解读和响应式布局。
- 站点只消费 `public.json`；生成数据和静态构建产物保持 gitignored，不进入公开仓库历史。
- 新增 `tools/deploy_report_site.py`，支持 nvm Node.js、Astro 构建、Cloudflare Pages Direct Upload 和 `--dry-run`。
- 当前 Hugo `site/`、`convert_reports_to_hugo.py` 和 `run_weekly.sh` 保持不变，待 Astro 站点验收后再切换或废除。
- 构建验证：Astro type check 通过；使用 `papers-20260823` 生成首页、报告详情页和 16 篇论文内容。

## 2026-08-24：收敛总结报告中的内部元数据与空方法输出

- 报告渲染不再显示 `study_type: mixed` 和局限 `basis: explicit/inferred` 等机器枚举；局限的
  `impact` 改为接在同一条目中，不再生成嵌套无序列表。
- 总结 schema 规范化会丢弃 `limitation: 未提供` 这类无意义记录，避免出现“局限 1: 未提供”。
- Phase F 质量门禁新增方法区检查：`method` 以及方法/设置/分析字段不能整体为空；失败响应等待
  重试，不会以 success 进入报告。同步强化 summary prompt，允许没有充分依据时输出空的
  `limitations` 数组。

## 2026-08-24：离线测试覆盖率基线与边界补测

- 检查发现原有测试虽全部通过，但没有覆盖率门禁；使用项目指定的
  `/path/to/paperscrawler-venv` 环境测得 361 个测试、约 51% 综合覆盖率。
- 新增离线 mock 测试，覆盖 LLM 重试/熔断、Phase C/E/E2/E3/F/G/H 的关键成功与异常路径、
  MinerU 轮询和 ZIP 解压、RSS/CrossRef、配置加载、报告快照与 WebUI 文件安全边界。
- 当前全套离线测试为 406 个用例，覆盖率约 82%（分支覆盖约 74%）；`.coveragerc` 将
  80% 作为可执行门槛，后续仍需优先补齐数据库迁移、Publisher 浏览器适配和剩余 Phase F/工具
  CLI 分支，不能把当前结果表述为 100% 全覆盖。
- 覆盖率命令固定为：
  `pytest tests/ --cov=src --cov-branch --cov-report=term-missing`。

## 2026-08-23：总结质量门禁与历史公式修复

- 审计 120 条 Phase F success 结果时发现，JSON 合法不等于内容完整；少数结果只有一句话，另有模型把 `\\beta`、`\\frac`、`\\times` 解码成控制字符，部分文本仍使用 `$...$` 或复杂环境。
- `summary_schema` 新增确定性伪转义/美元公式修复和 `summary_quality_issues()`；Phase F 现在会拒绝缺少具体结果或实质内容不足的响应。
- `fix_summary_formulas.py` 改为递归处理 schema v3 的全部文本字段，使用独立 FormulaFixer 配置和并发 worker；`reset_pipeline.py reset-summary` 新增 `--dois`，可只重跑异常论文。

## 2026-08-23：FormulaFixer 独立配置与并发

- 原实现把 FormulaFixer 放在 Phase F 主线程中逐篇、逐文本节点调用，并复用相关性角色的 LLM 配置，导致总结请求虽有并发，公式修复仍串行等待。
- 新增 `formula_fix.llm` 和 `formula_fix.concurrent_max`；FormulaFixer 任务使用独立线程池和独立模型配置，每个任务拥有自己的 HTTP Session，并使用单独的熔断器。
- FormulaFixer 仍通过 `needs_fix()` 跳过正常文本；单个修复失败回退原文本，不影响论文总结写入。默认本地配置使用 `mimo-v2.5`、关闭思考、最多 10 个修复 worker。

## 2026-08-23：兼容 OpenCode Zen Responses API

- 从日志确认 Muse Spark 1.2 Contributor 的 Phase F 请求错误发送到
  `/zen/go/v1/chat/completions`，OpenCode 返回 HTTP 403；该模型实际使用
  `/zen/go/v1/responses`。
- 新增 `openai_responses` 协议：将 system prompt 转换为 `instructions`、其余消息转换为
  `input`，将 JSON 输出格式转换为 `text.format`，并兼容 Responses API 的 `output_text`
  和 `output[].content[].text` 响应。
- 当前本地 `configs/settings.yaml` 的 summary 角色已切换为
  `muse-spark-1.2-contributor` + `openai_responses`；相关性角色仍保持 Chat Completions。
- 增加请求体、端点和响应提取回归测试；Responses 与 Chat/Messages 协议继续由角色级配置选择。

## 2026-08-23：兼容 MiniMax M3 的非严格 JSON 返回

- MiniMax M3 切换后确认 OpenCode Go 的 Chat Completions 请求可返回 HTTP 200，但部分回答仍带
  Markdown JSON 围栏、裸 LaTeX 反斜杠或字符串内未转义英文引号，导致旧解析器把成功响应误判为失败。
- `common.fix_json_invalid_escapes()` 现在先提取 JSON 对象、去除围栏，再修复有限范围的非法反斜杠和正文引号；新增回归测试覆盖 fenced JSON 和 `"peeler"` 类文本。
- 同时修复 4xx 错误响应正文未记录的问题：`requests.Response` 对 4xx 的布尔值为 false，错误详情必须用 `is not None` 判断响应对象。

## 2026-08-23：pipeline review 修复

- 修复 `--all`/默认全流程未真正覆盖 `SKIP_PHASE_*` 的问题；强制运行会临时覆盖阶段内部 flag，并在结束后恢复配置。
- CLI 现在会将阶段错误转换为退出码 1，避免 cron 在 pipeline 失败时误报成功。
- 修复本地 PDF 导入、人工审核 `uncertain`、Phase C 全局限额和 Phase F 无效 pending 队列。
- WebUI 的已总结筛选改为 SQL 过滤并同步分页总数；Dashboard 增加初筛和报告状态；数据库迁移只忽略明确的重复列错误。
- cron 包装脚本改为可版本控制，并支持 `PAPERSCRAWLER_PYTHON` 覆盖 Python 路径。
- 新增对应回归测试；指定环境下完整 pytest 通过 352 项，compileall、dry-run、关键 lint 和 shell 语法检查均通过。

## 2026-08-23：统一元数据清洗与 Phase F 总结 schema v3

- 定位 IOP DOI `10.1088/1361-6587/ae81e4` 的摘要问题：页面把换行序列以字面量
  `&#xD;` 写入数据库，旧的空白压缩逻辑无法识别，最终报告出现 `&#xD;`。
- 新增 `common.clean_extracted_text()`，统一处理实体解码、双重编码、控制字符、
  Unicode 规范化和断行连字符；RSS、CrossRef、Publisher、数据库写入、E/E3 输入和
  ReportSnapshot 均接入，保留 `×`、`◦` 等科学符号。
- Phase F 提示词和解析改为 schema v3。动机、方法、结论使用固定 key，主要结果是带
  唯一 `key` 的数组并拆分 finding/evidence/physical_interpretation；新增独立的
  limitations 数组，区分作者明确局限与保守推断；报告不再依赖 LLM Markdown 标题，旧
  字符串格式读取时自动兼容转换。
- 公开 JSON 的报告封装升级为 `schemaVersion: 2`，并独立标记
  `summarySchemaVersion: 3`；`content.papers[].summary` 作为唯一规范结构，便于静态报告以外的程序分析，
  `sections` 仅作为兼容投影保留。
- 新增实体清洗、IOP 回归和 schema 兼容测试。当前环境未安装完整 requirements，依赖
  `bs4`/`parsel`/`jinja2` 的测试需在项目虚拟环境中执行；纯 Python 清洗/schema 测试已通过。
- 数据库初始化增加幂等 `normalize_metadata_text()` 迁移；本地库本次已修复 2353 行历史标题/摘要。

## 2026-08-22：关键词目录与相关性 benchmark

- 将师兄师姐提供的 plasma lens、放电毛细管/等离子体通道、诊断、FLASH、闪烁体、束流光学、active plasma focusing、EMP、post-acceleration、PIC 等兴趣点加入 `configs/keywords.yaml` 的 `keyword_catalog`，并映射到现有子域。
- 保留 `scope_definition` 作为 LLM 的领域化分类依据；关键词目录只负责术语/别名管理、覆盖审计和 Prompt 召回提示，避免“命中一个词就判相关”。
- 新增 `tools/keyword_audit.py`，可检查重复术语、空映射、未知子域，并对标题/摘要 JSONL 统计实际命中。
- 新增 `benchmarks/relevance_gold.jsonl` 和 `tools/evaluate_relevance.py`，输出四分类混淆矩阵及 A/B 对 C/D 的 precision、recall、F1；也支持直接读取最新 WebUI 人工审核记录。
- 当前本地数据库尚无可用于评估的人工审核样本时，工具报告样本数为 0；这表示“尚未评估”，不代表筛选效果良好。

## 最近变更

### 2026-08-22：日志改为按日分文件

- 新增 `src/logging_config.py`，统一 CLI、兼容入口和 WebUI 的日志初始化。
- 日志写入 `data/logs/PaperCrawler-YYYY-MM-DD.log`，单日文件 10MB 后最多产生一个大小轮转备份，旧日志保留 14 天。
- 修复 WebUI 使用普通 `FileHandler`、不会轮转的问题；旧的 `data/PaperCrawler.log` 不再继续增长。

### 2026-08-22：新增日志统计与筛选工具

- 新增 `tools/log_report.py`，默认汇总当天 WARNING/ERROR，输出级别总数、来源统计、高频消息和最近明细。
- 支持 `--days`、`--date`、`--level`、`--contains`、`--summary-only` 和 `--json`，将原本的手工 `cat | grep` 流程变为可复用命令。
- 日志解析会合并大小轮转文件和多行异常详情；JSON 输出便于后续接入监控或脚本。

### 2026-08-22：ntfy 增加紧凑故障摘要

- 通知正文改为移动端紧凑布局，保留运行状态、耗时和阶段状态，并按阶段/问题类型合并 WARNING/ERROR。
- 将日志中的问题区分为抓取、PDF/MinerU、LLM、通知和其他问题；数据库阶段错误也会纳入摘要并脱敏。
- 使用 `fulltext_download_events` 按 DOI 记录最近 14 天的 E2 下载失败日期；同一 DOI 连续 2 天提示关注，连续 3 天标记需人工干预，不合并不同 DOI，也仍只发送一次最终通知。

### 2026-08-22：删除旧调度脚本并补齐工具文档

- 全仓确认 `tools/schedule_daily.py` 和 `tools/schedule_weekly.py` 没有被活动代码、cron 包装脚本或测试调用。
- 删除两个旧兼容入口；日常和每周调度统一使用 `tools/run_pipeline.py --daily/--weekly`。
- `docs/usage.md` 增加完整工具总览、常用命令、JSON 导出、多来源导出和工具弃用说明。
- 旧调度脚本相关内容保留在 `docs/archive/`，作为历史记录，不再作为当前用法。

### 2026-08-21：统一 JSON 快照与 Markdown 报告

- `tools/preview_report.py` 新增 `--before-date YYYY-MM-DD`，按论文 `created_date` 严格筛选早于截止日的文章。
- 自动报告和预览报告统一先生成结构化 `.public.json` 快照，再从同一份报告数据渲染 Markdown。
- 预览报告新增 `--export-public`，可将自动报告与当前预览目录的 sidecar 合并同步到公开站点。
- 导出器支持多个 sidecar 来源目录，并按报告 ID 清理自身拥有的历史文件，避免预览导出删除自动报告。
- 日期筛选可与 `all`、`week`、`today` 范围组合，且继续保持预览报告不修改数据库的行为。
- 例如生成本周以前的报告时，以本周一作为截止日：`--scope all --before-date 2026-08-17`。

### 2026-08-20：LLM 多协议传输层

- 增加 `openai_chat` 和 `anthropic_messages` 两种协议，端点、请求头、请求体和响应提取统一由 `common` 适配。
- 每个 LLM 角色可单独设置 `protocol`；旧配置省略该字段时保持 Chat Completions 行为。
- 真实测试确认 OpenCode Go 的 Minimax M3 在 Chat 请求中使用 `thinking.type=enabled` 会返回 400；生产总结配置切换到 Messages 协议并使用 `thinking: disabled`，避免思考块污染严格 JSON。
- 公式修复也改用公共适配层，避免协议切换后仍固定读取 `choices`。

### 2026-08-20：Phase C 末级代理 fallback

- 常规页面抓取重试全部失败后，可通过 `publisher.fallback_proxy_url` 配置代理 URL，使用新浏览器上下文对当前论文再尝试一次。
- fallback 成功按正常 `success` 状态写库并清零连续失败计数；失败继续保存错误快照并遵守 Publisher 连续失败熔断。
- 默认运行配置使用 `http://127.0.0.1:7890`，示例配置留空表示关闭。

### 2026-08-20：文档体系精简

- 将详细历史文档移动到 `docs/archive/`，核心文档只保留当前有效信息。
- `usage.md` 聚焦入口、配置、工作流、工具和故障排查。
- `design.md` 聚焦当前架构、Schema、安全边界和关键决策。
- `tasks.md` 聚焦近期上下文，避免历史实施细节干扰当前开发。

### 2026-08-20：相关性人工审核 WebUI

- 新增 `/relevance-review` 队列和详情页。
- 新增 `relevance_reviews` 追加式 SQLite 审计表。
- 审核结论不覆盖 LLM 原始结果；全文读取限制在 `data/` 目录内。

### 2026-08-19：ntfy 通知精简

- 通知只保留运行状态、总耗时和阶段结果。（后续已由 2026-08-22 的紧凑故障摘要补充问题类型和连续失败提醒。）
- 详细错误查看 `data/logs/PaperCrawler-YYYY-MM-DD.log`、`python tools/log_report.py` 和 HTML 错误快照。

### 2026-08-18：Cron 入口统一

- `run_daily.sh` 使用 `tools/run_pipeline.py --daily`。
- `run_weekly.sh` 使用 `tools/run_pipeline.py --weekly`，随后执行 Hugo 部署。

## 当前关键决策

| 主题 | 当前决策 |
|---|---|
| 相关性 | E 高召回，E3 全文终审；只有最终 A/B 进入报告 |
| 全文下载 | 使用持久化自然日配额，失败也计数 |
| 报告 | 统一 JSON 快照为规范化产物，Markdown 为展示投影；自动报告和预览报告分离，预览不改数据库 |
| WebUI | 监控、阅览和人工审核；不运行流水线、不编辑配置 |
| 配置 | YAML + `.env`；运行时通过 `CFG` 读取 |
| 重试 | daily 自动重置 failed，accepted/non-research 等合法跳过不强制重试 |

## 当前待关注事项

- Publisher 反爬策略可能随站点变化，需要观察 `data/raw/page/error/`。
- MinerU/PDF 配额和代理失败会延迟 E3，不应通过摘要绕过全文门槛。
- WebUI 只适合内网；公网访问需要代理层认证、TLS 和访问控制。
- 真实 API 测试会消耗配额，应优先使用离线 pytest。

## 文档导航

- [`README.md`](../README.md)：项目首页。
- [`docs/usage.md`](usage.md)：当前使用手册。
- [`docs/design.md`](design.md)：当前架构设计。
- [`docs/archive/`](archive/)：完整历史文档和流水账。
