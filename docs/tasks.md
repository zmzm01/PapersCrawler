> 此文档记录执行步骤、关键决策和经验教训。是精炼的上下文。

# 变更汇总

| 模块 | 变更 | 日期 |
|------|------|------|
| **run_weekly.sh 修复** | crontab 下 `--hugo --deploy` 缺 `--all`（只转最新一篇）→ 修复为 `--all --hugo --deploy`；crontab PATH 极简找不到 `hugo`(需 `/usr/local/bin`) 和 `ghp-import`(需 conda bin) → 新增 `export PATH`；`docs/README.md` crontab 示例同步修正 | 06-28 |
| **Hugo 站点样式增强** | 3 项样式修改：1) 卡片摘要优先使用 `.Description`（显示「日期—共收录 N 篇论文」而非正文片段）；2) 侧栏目录（sticky 260px，仅 h2 层论文标题，scroll-spy 高亮）；3) 文章页正文加宽至 `1100px`（不波及主页列表页）；对应 `convert_reports_to_hugo.py` 的 `_build_description`/`_count_papers` | 06-28 |
| **Optica Accepted Paper 检测** | `OpticaScraper.parse_page()` 新增 Accepted Paper 检测：检测 `#articleBody` 内 `<em>accepted for publication</em>` 特征时抛 `AcceptedPaperError`；`docs/design.md` 新增「9b. Optica」节描述检测策略与页面特征。 | 06-20 |
| **Announcement 非研究关键词** | `CFG.NON_RESEARCH_KEYWORDS` 新增 `"announcement:"` 前缀，AIP Announcement 类（如 `Announcement: Physics of Plasmas Early Career Collection 2025`）在 Phase C pre-fetch 阶段即被过滤删除并记入 `skipped_dois`。`docs/design.md` 四级关键词表同步更新。 | 06-20 |
| **PDF 下载三级兜底** | `BasePublisherScraper.download_pdf()` 新增第三级兜底：浏览器导航下载（`goto + expect_download`），模拟用户点击"Get PDF"按钮触发浏览器原生下载事件，解决 Optica `viewmedia.cfm` 仅响应导航请求的反热链接策略。双路径→三级兜底链（requests → JS fetch → browser navigation）。`docs/design.md` 同步更新下载策略节。148 pytest 全通过。 | 06-20 |
| **Hugo 报告部署** | 新增 `site/` Hugo 骨架、`tools/convert_reports_to_hugo.py` 转换脚本（--report/--all/--hugo/--deploy/--dry-run）；`run_weekly.sh` 一键报告+邮件+部署；`site/` 不提交 git，gh-pages 由 ghp-import 自动管理；141 pytest 全通过 | 06-16 |
| **Optica CrossRef 驱动 Phase C 跳过** | Optica 是 OA 期刊，CrossRef 返回完整 abstract。Phase C 新增 skip：对 `cr_metadata_fetched_status='success'` 且有 abstract 的 Optica 论文直接标记 `skipped`，跳过浏览器。Phase E2 新增 `OpticaScraper` 延迟页面访问补齐 `pdf_url`。DB 新增 `update_publisher_pdf_url()` 只更新 pdf_url 不覆写 Phase C 状态。 | 06-16 |
| **报告增强** | Markdown/HTML 报告新增期刊名、出版社、匹配子领域；`phase_g.py` paper_dict 增加 4 个字段；`paper_report_generator.py` 元信息区同步渲染 | 06-15 |
| **报告简化** | 去除大分类分组（用户反馈不实用）；改为按期刊+日期排序；去除来源行（discovery_source）；匹配子领域改用中文短标签（_build_subdomain_labels）；`_make_markdown_section` 支持动态 heading_level | 06-16 |
| **子领域输出规范化** | `build_default_prompt()` JSON 示例改用真实 `scope_definition` 中的 key（替代虚构的 "Laser Wakefield Acceleration"）；`relevance.yaml` 增加"Use exactly the sub-domain keys"指令；`phase_e.py` MatchedSubfields 增加 post-processing（小写化、空格→下划线、含标点清理、已知 key 校验），5% 的格式偏差问题已覆盖 | 06-16 |
| **子领域判断精度修复** | 根据用户反馈调查发现：`plasma_physics` 作为默认项被过度使用（80%）、ICF 聚变论文被误标为 A+plasma_physics、Corrigendum 漏网。修复：`relevance.yaml` 重写 Task — 子领域改为可选（最多 2 个、按关联度排序）、irrelevant_fields 升级为判定规则（匹配即 D）、context_gates 优先于 scope_definition 约束子领域分配；`settings.yaml` NON_RESEARCH_KEYWORDS 增加 "corrigendum" | 06-16 |
| **CFG 重构** | 运行时配置从模块级裸变量迁移到 `CFG` 持有对象（`types.SimpleNamespace`），消除 `reload_config()` 的 `global` 声明与模块级值副本过期问题。`_apply_settings()` 抽取去重（消除模块加载和 reload 之间 ~80 行重复代码）。删除废弃的 `SKIP_PHASE_A`。全项目 19 个文件更新为 `from config import CFG; CFG.X` 模式。 | 06-11 |
| **Publisher 统计过滤** | Phase H `detailed.html` 邮件模板中的 publisher 爬取统计现在排除未启用的 publisher（如 Optica `enabled: false` 不再显示 "0 success"），从 `load_publishers()` 构建 `enabled_publishers` set 做过滤 | 06-11 |
| **Pre-fetch 非研究论文检测** | Phase C 新增浏览器启动前的标题前缀检测：从 DB 读取论文标题，按 `settings.yaml` 配置的前缀列表（`erratum`, `author correction:`, `publisher correction:`, `comment on`, `response to`, `publisher's note`）前缀匹配后直接 `delete_paper()` 并记入 `skipped_dois`；post-fetch 同步从子串匹配改为前缀匹配 + config 驱动；pre/post 独立开关，关键词列表用户可配置 | 06-11 |
| **schedule_daily CLI 开关** | 新增 `--no-reset-publisher` 和 `--no-reset-mineru` 参数（默认均开启重置）；新增 `_run_auto_reset()` 函数封装重置逻辑；日志分别记录各重置开关状态 | 06-10 |
| **Keywords YAML 重构** | keywords.yaml 从 6 子域重整为 4 大方向（加速/等离子体/束流应用/先进技术与AI），新增全局 context_gates 消歧层，LWFA 注释保留，sub_domains_embedding 同步更新；`build_scope_block()` 重构支持 3 层渲染；`PaperRelevanceChecker` 和 Phase H 适配新签名 | 06-14 |
| **skipped_dois 表** | 新增 `skipped_dois` SQLite 表（doi PRIMARY KEY, reason, created_date），记录被永久删除的论文 DOI；Phase A 发现前同时检查 `paper_doi_exists()` 和 `is_doi_skipped()`；Phase C NonResearchPageError 先 `insert_skipped_doi()` 再 `delete_paper()`（AcceptedPaperError 仅删除不入 skipped_dois，因同 DOI 正式版会重新出现） | 06-10 |
| **Science og:type 非研究检测** | `ScienceScraper.parse_page()` 当 `dc.Type` 缺失时增加 `og:type` 三级兜底：`og:type` 存在则视为非研究文章（Careers/Working Life 等无 dc.Type 但有 og:type），抛 `NonResearchPageError`；两者均不存在才抛 `PageParseError`（页面结构可能已变） | 06-10 |
| **Nature Client Challenge 检测** | `phase_c.py` bot 检测模式增加 `"javascript is disabled"`（HTML 内容）和 `"client challenge"`（页面标题）关键词，覆盖 Nature 自有 JS 验证拦截页。同时加入异常处理器 `is_bot` 检测（此前仅在空解析结果路径检测），且新增 `og:type` 对应标题信息提取 | 06-10 |
| **MinerU OSS 403 最终修复** | `_upload_file()` 严格遵循 MinerU 官方文档（`No Content-Type header is required when uploading files`），改用 module-level `requests.put(url, data=data)` + 手动重试循环。不经过 `self._session`（带 JSON Content-Type 导致 403），不设自定义 Content-Type（OSS 签名与 `application/octet-stream` 匹配） | 06-10 |
| **first-in-group 日志格式** | 首个论文 `retry_attempts = [2]` 的日志从 `attempt 3/1` 改为 `attempt 1/1`，清晰表示单次 45s 尝试 | 06-10 |
| **非论文页删除** | NonResearchPageError 处理从 cascade skip 改为 `db.delete_paper()` 直接删除，与 AcceptedPaperError 一致 | 06-10 |
| **日志轮转** | 3 个入口点（`main.py`/`schedule_daily.py`/`schedule_weekly.py`）的 `FileHandler` 替换为 `RotatingFileHandler`（10MB × 5 backup） | 06-10 |
| **邮件 HTML 模板** | 新增 `templates/email/default.html`（字段：report_title/paper_count/has_papers）；`phase_h.py` 改用 HTML 模板渲染 + `body_type="html"`；`settings.yaml` 新增 `email.template` 配置；WebUI Config 页支持模板名覆盖 | 06-10 |
| **自动重试** | `schedule_daily.py` 入口自动重置 `publisher_page_fetched_status = 'failed'` → `pending`，使失败论文在每次每日运行时自动获得重试 | 06-10 |
| **PDF 复用** | Phase E2 增加本地 PDF 复用：`paper.pdf` 已存在且有效时跳过下载，仅校验 `%PDF-` 头部；无效时删除重下 | 06-09 |
| **Phase C 反爬检测重构** | 移除 parse_page() 前的 CF 预检（误判 APS/AIP 含 CF CDN 脚本的正常页面）；bot 检测移至 parse_page() 之后，仅当 title+doi+abstract 全空时才检查；新增 Radware Bot Manager / captcha 检测（HTML + `<title>`）；异常处理中也增加 bot 检测（bot 拦截导致的异常走完整重试而非 attempt 0 终止）；修复 first-in-group 日志硬编码 `/3` → `len(retry_attempts)` | 06-09 |
| **MinerU OSS 403 修复** | `_upload_file()` 改用独立 `requests.Session()`（不继承 `self._session` 的 `Content-Type: application/json`），显式设置 `Content-Type: application/pdf`；OSS 预签名 URL 对 Content-Type 敏感，JSON header 导致签名校验失败 | 06-09 |
| **PDF 下载即保存** | `phase_e2.py` PDF 下载后立即保存到 `MINERU_OUTPUT_DIR/<safe_doi>/paper.pdf`（不再用 tempfile），MinerU 上传失败时 PDF 不丢失；新增 `%PDF-` 头部校验，非 PDF 内容直接报错；移除 `tempfile`/`shutil` 导入和 `pdf_path` 清理逻辑 | 06-09 |
| **架构改进** | 全面 review + 8 项架构修复：Phase 级异常保护、force 参数拆分、消除重复常量、原子写入、FormulaFixer 注释确认、Logger 统一（支持 LOG_LEVEL）、ConfigManager reload_config()、去除 mineru_fulltext 冗余存储 | 06-07 |
| **Bug 修复** | 修复 review 指出的 9 个 bug：_get_reset_cols 列过滤错误、DB 连接泄漏、fetch_by_journal 零重试、error HTML 保存缺失、PredictedCategory 静默归 D、配置加载无文件缺失保护、RSS 零重试、MinerU 零重试、CF 检测增强 | 06-07 |
| **Accepted Paper 处理** | Phase C 检测到 Accepted Paper 时从 cascade skip 改为 `delete_paper()` 直接删除；新增同名 DB 方法；新建 `tools/delete_accepted_papers.py` 清理脚本（支持 `--dry-run`/`--force`） | 06-06 |
| **每日/每周调度脚本** | `runner.py` 新增 `DAILY_PHASES`/`WEEKLY_PHASES` 常量和 `run_daily()`/`run_weekly()` 方法；新建 `tools/schedule_daily.py`（A→F）和 `tools/schedule_weekly.py`（G→H），适配 cron | 06-07 |
| **WebUI 修复** | Home 页标题图标间距增大；Papers 页适配 A/B/C/D 四级分类（badge + 图例 + skipped 置底）；新建 `md_to_pdf_katex.py`（KaTeX + cloakbrowser PDF 渲染，支持 \(\)/\[\] 公式） | 06-07 |
| **Optica 反爬检测** | OpticaScraper.parse_page() 增加非 CF 反爬检测（title 有值但 abstract 空且 #articleBody 缺失时抛 PageParseError）；reset_empty_abstract.py 扩展重置 Phase C | 06-07 |
| **PDF 下载重构** | `download_pdf()` 下载顺序反转（requests+cookie 优先 → JS fetch 兜底）；APS 导航容错（wait 5s→15s + try/retry）；UA 获取加 try 保护 | 06-07 |
| **Phase F 修复** | `phase_f.py:43` `sqlite3.Row` 对象无 `.get()` 方法 → `p["llm_relevance_category"]` 方括号访问；`mineru_paper_parser.py` `print()` → `logger.info()` 残留修复 + `_download_and_extract()` 改用流式下载（`stream=True` + 分块写入，避免大 zip 整体加载到内存） | 06-07 |
| **研究领域定义重构** | `keywords.yaml` 改为 `scope_definition`（6 子领域中文描述+topics）+ `irrelevant_fields` + `sub_domains_embedding`（英文 <300w）；`PaperRelevanceChecker` 改用 scope_definition 构建 prompt；LLM 输出改为四级分类 A/B/C/D；DB 新增 `llm_relevance_category`/`llm_relevance_subfields` 列；`get_relevant_papers()` 查询条件改为 `IN ('A','B')`；**99 passed** | 06-06 |
| **Review Bug 修复** | 修复 review 指出的 5 个问题：config_save_prompt 缺参数、fix_json_invalid_escapes 双重调用、Phase E2 无代理、DOI 路径穿越、Phase B 重复代码分支 | 06-06 |
| **WebUI 图标美化** | Font Awesome CDN 全局图标；侧边栏导航图标；按钮/卡片/架构图图标；新增 `.icon-mr`/`.icon-left` 样式 | 06-05 |
| **Home 页重构** | 项目介绍（7 出版社 21 期刊说明）+ 技术栈标签 + 架构概览图（两行 10 阶段流水线）+ Quick Start（3 步卡片）+ 图标装饰 | 06-05 |
| **订阅管理** | 新增 `subscribers` DB 表（email/name/active/delivery_method）；Phase H 改为 DB 收件人优先、回退 `.env`；WebUI 订阅页（添加/删除/启用停用/测试/从 .env 导入） | 06-05 |
| **Nature 过滤** | `phase_a_crossref()` 补充 `/d41586-` 过滤（双路径覆盖）；增加 `insert_paper_created_date()` 调用 | 06-05 |
| **APS Accepted Paper** | 新增 `AcceptedPaperError` 异常；`APSScraper.parse_page()` 检测 URL 含 `/accepted/` 或特征标签时抛出；`phase_c.py` 捕获后 cascade skip 下游；不专门适配 selector | 06-05 |
| **Logger 作用域** | `paper_relevance.py` 中 `logger = logging.getLogger(__name__)` 从 `call_deepseek_api()` 内部移至模块级别，修复 `cannot access local variable 'logger'` 崩溃 | 06-05 |
| **错误诊断** | `fetch_page()` 异常时保存 HTML 快照到 `data/raw/page/error/`；失败出口增加错误类型、页面标题、HTML 路径汇总日志 | 06-05 |
| **Session 清理** | `BasePublisherScraper.close()` 新增 `shutil.rmtree()` 自动清理 session 缓存 | 06-05 |
| **CLI/WebUI 隔离** | `_journal_effective()` 修复 publishers.yaml `enabled` 回退；`phase_a_rss`/`phase_a_crossref` 加 `use_overrides` 参数；runner 传 force，CLI 不加载 journal_overrides.json | 06-05 |
| **Phase C disbled 跳过** | `phase_c_publisher()` 签名加 `publishers` 参数；构建 `enabled_publishers` 集合；禁用 publisher 的 pending 论文直接标记 `skipped`，不浪费浏览器启动时间 | 06-05 |
| **ISSN 去重** | `phase_a_crossref()` 加 `seen_issns` 集合，相同 ISSN 只请求一次 CrossRef API | 06-05 |
| **AIP PDF 回退链** | `download_pdf()` 最终方案：`fetch()` → `requests` + 浏览器 cookie/UA（逃了两条弯路才到）；移除了无效的 `expect_download` + `<a click>` | 06-05 |
| **Science altmetric** | `ScienceScraper.parse_page()` 增加 `altmetric_type` meta 检测，覆盖 CrossRef 发现的非研究文章（此前只有 RSS 路径的 dc.Type 检测） | 06-05 |
| **Reset 规范化** | 新增 `reset-relevance` 子命令；全部 6 子命令 `-h` 输出统一格式（影响列/不受影响/级联） | 06-05 |
| **goto 超时** | `download_pdf()` context-establishing `goto(page_url)` timeout 从 60s 提升到 120s（与 fetch_page 一致） | 06-05 |
| **MinerU 轮询日志** | `_poll_batch()` 的 3 处 `print()` 改为 `logger.info()`，日志写入文件 | 06-05 |
| **YAML 注释保留** | `config/save-domain` 改用 `ruamel.yaml` 替代 `pyyaml` 的 `yaml.dump()`，避免 domain_description 编辑时丢失 keywords.yaml 中的注释 | 06-04 |
| **Web UI 定位** | 明确 Web UI = 监控仪表盘 + 报告工作站，非 CLI 替代；配置隔离（CLI 用 config.py，Web UI 用 skip_overrides.json，互不干扰）；SKIP 切换从"仅影响 CLI"改为"仅影响 Web UI Pipeline 页" | 06-04 |
| **Web UI 新增** | 新增 Data Sources 页面（期刊启用/禁用 + RSS/CrossRef 独立开关，写入 data/journal_overrides.json）；Config 页增加 domain_description 文本框 + 连通性测试按钮 + MinerU Token 过期色标 | 06-04 |
| **Web UI 修正** | Pipeline 页跳过阶段按钮灰显 + 不可点击 + 后端返回 400；Papers 页改为日期排序（入库/发表日期选择）+ 语义分列/LLM 相关性列；修复 home 页和 js i18n 中过时的 SKIP 描述 | 06-04 |
| **Phase A** | 新增 `_load_journal_overrides()` / `_journal_effective()` 支持 Data Sources 页面设置的期刊级开关 | 06-04 |
| **双源发现** | Phase A 拆为 A-RSS + A-CR 双路径；新增 fetch_by_journal() 按 ISSN+日期范围查询；新增 discovery_source 列跟踪每篇论文的来源；publishers.yaml 所有期刊增加 ISSN | 06-04 |
| **Phase D 重构** | Phase D 改为参考排序模式（不参与过滤）；模型升级 bge-base-en-v1.5；子领域分离；SKIP_PHASE_D 默认开启；语义分与 LLM 判断解耦 | 06-04 |
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
| **报告日期过滤** | `get_papers_for_report()` 改用 `report_date IS NULL` 替代 `report_status = 'pending'`；`reset-report` 新增 `--days` 参数支持按日期范围重置 | 06-03 |
| **SMTP 加固** | `email_sender.py`: 连接移入 try/except + 1 次重试 + STARTTLS 后 ehlo() + quit 保护网易邮箱 SSL 端口配置修正 | 06-03 |
| **SKIP 隔离** | Web UI 的 `skip_overrides.json` 不再影响 CLI（`runner.py` 仅 `force=True` 时加载 overrides） | 06-04 |
| **配置合并** | email 配置从 `configs/email.yaml` 完全合并到 `.env`；删除 `email.yaml.example`；`load_email_config()` 改为从 `os.getenv` 读取 | 06-04 |
| **FormulaFixer 重构** | `LLMFormulaFixer` → `FormulaFixer`：JSON in/out 改为纯文本 in/out，新增 `needs_fix()` 预检测 + 逐字段修复 + module-level logger | 06-03 |
| **独立修复工具** | 新增 `tools/fix_summary_formulas.py`，支持 `--doi` / `--publisher` / `--dry-run` / `--verbose`，无需重跑 Phase F | 06-03 |

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

## LLM 公式格式修复（v1 — JSON in/out，已弃用）

**动机**：LLM 指令遵循不到位，部分 LaTeX 命令（`\times`、`\mathrm` 等）未用 \(` 包裹。正则方案边缘 case 过多，总有遗漏。

**v1 方案**：新增 `LLMFormulaFixer` 类，接收整个总结 dict 并用 `json_object` 模式修复。问题：LLM 需要同时处理 JSON 结构 + 双层反斜杠转义，输出质量不稳定，默认关闭。

## FormulaFixer 重构（v2 — 纯文本 in/out，2026-06-03）

**动机**：JSON 进/JSON 出的方案给 LLM 增加了不必要的转义负担（`\\\\(` vs `\\(`），LLM 频繁输出非法 JSON 导致修复失败。且原方案只能全量运行，无法单独对已有总结进行修复。

**v2 方案**：替换 `LLMFormulaFixer` → `FormulaFixer`，核心变化：

1. **纯文本进/纯文本出** — `json.loads()` 后的 Python 字符串（单反斜杠）直接送 flash 模型，LLM 只理解 LaTeX 语法，无需关心 JSON 结构
2. **预检测 `needs_fix()`** — 先移除已正确包裹的 `\(...\)` / `\[...\]` 区域，只对残留 `\command` 的字段调 API，大部分字段零成本跳过
3. **逐字段修复** — Phase F 中遍历 5 个文本字段逐个调用 `fix_text()`，Python 的 `json.dumps()` 自动处理写入 DB 时的 JSON 转义
4. **独立工具** — 新增 `tools/fix_summary_formulas.py`，无需重跑 Phase F，支持 `--doi` / `--publisher` / `--dry-run` 等参数
5. **Logger 补全** — 跳过/成功/失败三个出口均有日志记录

**数据流对比**：
```
v1: LLM JSON string → json.loads → dict 
     → json.dumps → flash(JSON in/out) → json.loads → json.dumps → DB

v2: LLM JSON string → json.loads → dict 
     → 各字段(纯文本) → needs_fix? → flash(纯文本 in/out) 
     → 放回 dict → json.dumps(自动转义) → DB
```

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

# 2026-06-03 — Report 日期过滤与按日期重置

**动机**：原有 `report_status` 是二进制状态（`pending` → `reported`），一旦标记就永久排除。同一天需要重试时，已报告论文锁定在旧报告中，重试成功的论文生成新报告，导致报告碎片化。

**解决**：`get_papers_for_report()` 改用 `report_date` 作为主要过滤条件，`reset-report` 新增 `--days` 参数支持按日期范围重置。

### Phase G — `get_papers_for_report()` 查询条件变更

- `report_status = 'pending'` → `report_date IS NULL`
- `mark_papers_reported()` 保持不变，仍同时写入 `report_status` 和 `report_date`
- `report_status` 保留为辅助标记，不影响报告汇入逻辑

### `reset-report` 新增 `--today` 和 `--days` 参数

```bash
# 重置今天（当前自然日）被报告的论文（无滑动窗口歧义）
python tools/reset_pipeline.py reset-report --today

# 重置最近 N 个自然日被报告的论文
python tools/reset_pipeline.py reset-report --days 3
```

- `--today`：仅重置今天（当前自然日）被报告的论文，查询条件：`date(report_date) = date('now', 'localtime')`
- `--days N`：按日历日重置最近 N 天的报告，查询条件：`date(report_date) >= date('now', '-N days', 'localtime')`
- `--today` 与 `--days` 互斥，同时指定时 `--today` 优先
- 不传 `--today` / `--days` 时保持原有行为（重置全部已报告论文）

### 同一天重试工作流

```bash
# 第 1 次运行，部分论文成功报告
python src/main.py

# 修复问题后，重置今天被报告的论文
python tools/reset_pipeline.py reset-report --today

# 重新运行 Phase F→G，生成合并后的完整今日报告
python src/main.py
```

# 2026-06-03 — SMTP 连接加固与网易邮箱 SSL 端口修正

**动机**：运行实时 SMTP 测试时 `SMTPServerDisconnected: Connection unexpectedly closed` 崩溃。两个根因叠加：
1. **配置错误**：网易邮箱 163.com 实际使用 SSL 465 端口，但 `configs/email.yaml` 配置为 TLS 587
2. **代码脆弱**：SMTP 连接代码在 `try` 块之外，连接异常直接穿透到调用方

**解决**：

### 配置修正 — `configs/email.yaml`

```
smtp_port: 587   →   465
use_tls: true    →   false
```

`use_tls=false` 时 `EmailSender` 使用 `smtplib.SMTP_SSL` 直连加密端口，不再走 STARTTLS 路径。

### 代码加固 — `src/processors/email_sender.py`

| # | 问题 | 现状 | 修复 |
|---|------|------|------|
| ① | 连接代码在 try 外 | `smtplib.SMTP(...)` 在 try 块之前，异常不捕获 | 整个连接 + 登录 + 发送并入单一 `try/except/finally` |
| ② | 缺少 ehlo() | STARTTLS 后未重新 EHLO（RFC 3207 要求），部分国内 SMTP 服务器握手异常 | `starttls()` 后加 `server.ehlo()` 显式重协商 |
| ③ | 无重试 | 瞬态 SMTP 失败直接崩溃 | 加 1 次重试（共 2 次），间隔 2s |
| ④ | finally 中的 server 未保护 | `server.quit()` 假设 server 已绑定 | `if server is not None: server.quit()` 加 try/except |

### 测试适配 — `tests/test_email.py`

TLS 模式 mock 断言增加 `mock_instance.ehlo.assert_called_once()`，验证 STARTTLS 后正确调用 EHLO。

# 2026-06-03 — Web UI 完善：可编辑 Config、Reset、Papers 页、报告勾选 + 预览

**背景**：用户反馈多个 UI 改进需求：
1. Config 页应为可编辑（SKIP 开关切换 + YAML 编辑器 + 二次确认）
2. Logs 页 Filter 有 bug（innerHTML 分割导致过滤后日志消失）
3. Report 应有论文勾选 + 预览 + 下载（而非简单的 publisher 下拉）
4. Pipeline 页需状态图表和 Reset 按钮
5. Dashboard 改为 Home 介绍页，新增 Papers 页面
6. Log filter bug 修复：改用 textContent 而非 innerHTML
7. Reset 时 E2/F/G 不应受 E 级联影响

**变更**：

### `src/web/app.py` — 新增 8 个端点
| 端点 | 功能 |
|------|------|
| `GET /` | Home 介绍页 |
| `GET /papers` | 按语义相似度排序的论文列表 |
| `POST /pipeline/reset/{phase}` | 批量重置阶段状态 + 返回影响统计 |
| `POST /config/skip-toggle/{phase}` | 切换 SKIP 覆盖（写入 data/skip_overrides.json）|
| `POST /config/save-publishers` | 语法校验 + 保存 publishers.yaml |
| `POST /config/save-keywords` | 语法校验 + 保存 keywords.yaml |
| `POST /report/generate` | 接受 DOI 列表，只生成选中论文的报告，返回预览 |
| `GET /report/download/{filename}` | 报告文件下载 |

### 前端 — 7 个模板重写
- `home.html` — 项目介绍 + 快速入口卡片 + 统计数字
- `pipeline.html` — CSS 柱状图、Reset 按钮（带确认对话框）、Live Log 级别过滤
- `papers.html` — 语义相似度排序列表（含可视化分数条）
- `report.html` — 论文勾选表格（Publisher 筛选、全选/取消）、生成后预览 + 下载链接
- `logs.html` — 修复 filter bug，改用 `textContent` + 原始文本分离
- `config.html` — 可点击 SKIP 开关、YAML 文本编辑器（语法校验 + 二次确认保存）
- `base.html` — 侧边栏更新为 Home/Pipeline/Papers/Report/Logs/Config

### 后端基础设施
- `src/db/database.py` — 新增 `get_papers_with_summaries()`、`get_papers_sorted_by_semantic()`、`count_reset_impact()`、`batch_reset_status()`
- `src/pipeline/runner.py` — `run_phases()` 读取 `data/skip_overrides.json` 叠加到 SKIP 配置
- `src/pipeline/phase_g.py` — 新增可选 `doi_list` 参数，支持只生成选中论文的报告

### 级联逻辑修正
- E 重置不再级联 E2/F/G（重新判定相关性不影响已有 PDF 全文和总结）
- E2 重置级联 F/G（重新解析 PDF 后旧总结可能失效）
- F 重置级联 G（重新总结后报告应更新）

# 2026-06-03 — CF 检测移至 parse_page 之前

**问题**：`phase_c.py` 中 CF 检测在 `parse_page()` 之后执行。当 Cloudflare 拦截 Nature 页面时，
`parse_page()` 找不到 `dc.type` meta 标签，抛出 "No dc.type in Nature page, maybe the page structure has changed"，
掩盖了真正的 CF 拦截问题。

**变更**（`pipeline/phase_c.py`）：
- CF 检测移至 `fetch_page()` 和 `parse_page()` 之间
- CF 拦截时显示 "Cloudflare detected (attempt X/3)" 并走重试逻辑
- 只有非 CF 页面才进入 `parse_page()`，避免误报页面结构变化

# 2026-06-03 — 报告分离：自动报告 vs 用户报告 + 推送无更新通知

**动机**：自动流水线生成日报用于邮件推送，Web UI 用户勾选生成临时报告。两者混用同一目录
`report_*.md` 命名，Phase H 取最新文件时可能误发用户报告。此外，无新增论文时不应推空报告。

**变更**：

### 目录分离

```
data/reports/
├── auto/        ← Phase G 自动日报（按日期覆盖）
└── user/        ← Web UI 用户自选报告（精确到秒）
```

### 文件改动

| 文件 | 改动 |
|------|------|
| `src/config.py` | 新增 `AUTO_REPORT_DIR` 和 `USER_REPORT_DIR` 路径常量 |
| `src/pipeline/phase_g.py` | 签名改为 `(db, auto_dir, user_dir, doi_list=None)`；自动模式写入 `auto/report_YYYYMMDD.md`（覆盖），标记已报告；用户模式写入 `user/report_YYYYMMDD_HHMMSS.md`，**不标记**已报告；无论文时直接 return 不创建文件 |
| `src/pipeline/phase_h.py` | 签名改为 `(auto_dir)`；检查 `auto/report_YYYYMMDD.md`；存在→作为附件发送；不存在→发送「本期无新增相关论文，无需关注」通知 |
| `src/pipeline/runner.py` | 创建 `auto/` 和 `user/` 目录；Phase G 传入双路径；Phase H 仅传入 `auto_dir` |
| `src/web/app.py` | `/report/generate` 向 `USER_REPORT_DIR` 写入；预览/下载也指向 `user/` |

### 推送行为

| 场景 | Phase G | Phase H |
|------|---------|---------|
| 有新增论文 | `auto/report_20260603.md` | 发送该文件为附件 |
| 无新增论文 | 不创建文件，log + return | 发送「本期无新增相关论文」通知（无附件） |
| Web UI 用户勾选生成 | 写入 `user/`，不标记已报告 | 不参与推送 |

# 2026-06-03 — FormulaFixer 增强：裸上下标检测 + force 强制模式

**动机**：`needs_fix()` 的旧正则仅检测 `\command` 模式（`\alpha`、`\times` 等），遗漏了仅含上下标的裸 LaTeX 公式（如 `E = m c^2`、`x_i`、`E_{kin}`），导致这些公式被判定为"无需修复"，跳过 LLM 修复流程。

**变更**：

**1. 正则增强**（`src/processors/llm_summarize_deepseek.py`）

旧：`r'\\[a-zA-Z]{2,}'` — 仅匹配 `\command`

新：
```
r'\\[a-zA-Z]{2,}          # \command 模式
 |[\w\)\]]\^[\w\{\(]      # 上标: c^2, x^{n+1}, )^2
 |[\w\)\]]_[\w\{\(]'      # 下标: x_i, E_{kin}, )_i
```

新增匹配的用例：

| 输入 | 旧行为 | 新行为 |
|------|--------|--------|
| `E = m c^2` | `needs_fix`=False → 跳过 | `needs_fix`=True → 送修 |
| `laser energy E_0` | `needs_fix`=False → 跳过 | `needs_fix`=True → 送修 |
| `x^{n+1} expansion` | `needs_fix`=False → 跳过 | `needs_fix`=True → 送修 |
| `\\alpha particles`（已正确包裹）| `needs_fix`=False → 跳过 | `needs_fix`=False → 跳过（不变）|

已知假阳性：`x_ray` 等含 `_` 的复合词也会触发，但在学术英文中此类写法极少（通常写作 "X-ray"），且即使误触发 LLM 也能正确处理。

**2. force 强制模式**

| 层级 | 变更 |
|------|------|
| `FormulaFixer.__init__()` | 新增 `force: bool = False` 参数 |
| `FormulaFixer.needs_fix()` | 新增 `force: bool = False` 参数，为 True 时跳过检测直接返回 True |
| `FormulaFixer.fix_text()` | 传递 `self.force` 给 `needs_fix()` |
| `src/config.py` | 新增 `FORCE_FORMULA_FIX = False` |
| `src/pipeline/phase_f.py` | `import FORCE_FORMULA_FIX` + 传给 `FormulaFixer(force=...)` |
| `tools/fix_summary_formulas.py` | 新增 `--force` CLI 参数，透传给 `FormulaFixer` |

使用方式：

```bash
# 仅修复正则命中的字段（默认行为）
python tools/fix_summary_formulas.py

# 跳过正则检测，强制修复全部字段
python tools/fix_summary_formulas.py --force

# Pipeline 中启用（config.py）
FORCE_FORMULA_FIX = True
```

**设计考量**：
- `force` 模式需要额外调用 flash API，逐字段送修。默认关闭，仅在正则无法覆盖时由用户按需开启。
- `force` 与 `SKIP_FORMULA_FIX` 语义正交：前者控制"是否检测"，后者控制"是否启用修复器"。

# 2026-06-03 — FormulaFixer FIX_PROMPT 重写：Unicode → LaTeX 转换

**动机**：LLM 输出的总结字段中常混入 Unicode 数学字符（希腊字母 `α β γ`、上标 `² ³`、运算符 `≈ ≠` 等），
这些字符在 Markdown 报告中显示为 Unicode 文本而非 LaTeX 渲染，格式不统一，且 PDF 转换时无法正确处理。

**变更**：

**1. FIX_PROMPT 重写**（`src/processors/llm_summarize_deepseek.py`）

旧 prompt 只处理 3 类问题：缺反斜杠分隔符、裸 LaTeX 命令、独立公式缺包裹。

新 prompt 增加第 1 类规则——Unicode 数学符号 → LaTeX 命令，包含：

| 类别 | 示例 | LaTeX 转换 |
|------|------|-----------|
| 希腊字母 | α, β, γ, δ, ε 及大写 | \alpha, \beta, \gamma, \delta, \varepsilon |
| 上标/下标 | ², ³, ⁰, ₀, ₙ, ₓ | ^2, ^3, ^0, _0, _n, _x |
| 关系运算符 | ≈, ≠, ≤, ≥, ≡ | \approx, \neq, \leq, \geq, \equiv |
| 二元运算符 | ±, ×, ÷, · | \pm, \times, \div, \cdot |
| 箭头 | →, ←, ⇒, ⇔ | \rightarrow, \leftarrow, \Rightarrow, \leftrightarrow |
| 其他常用 | ∂, ∇, ∞, ℏ, ∈, ∉, ∀, ∃, √, ∝, ∠, ⊥ | \partial, \nabla, \infty, \hbar, \in, \notin, ... |

并新增输出约束："输出中不应保留任何数学类 Unicode 字符，仅允许普通 ASCII 文本和 LaTeX 命令"。

**2. needs_fix() 正则增强**

新增 Unicode 数学字符范围检测：

```python
unicode_math = (
    r'[\u0370-\u03FF'       # Greek & Coptic
    r'\u2070-\u209F'        # Superscripts & Subscripts
    r'\u2190-\u21FF'        # Arrows
    r'\u2200-\u22FF'        # Mathematical Operators
    r'\u2100-\u214F'        # Letterlike Symbols (ℏ, ℓ)
    r'\u00B2\u00B3\u00B9'   # ² ³ ¹
    r']'
)
```

确保含 Unicode 数学符号的文本能触发修复器。

**3. FIX_PROMPT 改为 raw string 修复历史转义 bug**

旧 prompt 使用普通字符串 `"""..."""`，Python 将 `\alpha` 中的 `\a` 解析为 ASCII Bell（`\x07`），
`\beta` 中的 `\b` 解析为 Backspace（`\x08`），导致 LLM 长期收到损坏的示例文本。

改为 raw string `r"""..."""` 后，所有反斜杠保持字面值，LLM 正确接收到 `\alpha`、`\beta`、`\(` 等。

**关键设计保持**：
- 纯文本输入/纯文本输出（`json.loads()` 解码后的单反斜杠格式）
- 不引入 JSON 转义层，prompt 中的反斜杠始终是单层 `\`
- 修复失败时回退原始文本

# 2026-06-03 — SUMMARIES_PROMPT 禁止复杂 LaTeX 环境

**动机**：LLM 总结中可能使用 `\begin{cases}`、`\begin{aligned}` 等复杂 LaTeX 环境，
其中包含 `\\` 换行和 `&` 对齐符，经过 JSON → Python → Markdown 多层转义后极易出错，
且 FormulaFixer 和下游报告渲染均无法正确可靠地处理它们。

**变更**（`src/config.py` + `src/processors/llm_summarize_deepseek.py`）：

在 `SUMMARIES_PROMPT` 的内容要求中新增第 4 条：

```
4. 禁止使用复杂 LaTeX 环境：禁止 \begin{} / \end{}（如 cases、aligned 等），
   禁止 \\ 换行。公式仅限 \frac、\sqrt、\int、\sum、\partial 等基本命令
   及上标/下标/希腊字母。
```

原第 4 条（`\\n` 换行规则）顺延为第 5 条。

**设计考量**：
- `\text{}`、`\mathrm{}` 等简单文本命令仍允许（物理单位标注常用）
- `\begin{}` / `\end{}` 已被 `needs_fix()` 的 `\\[a-zA-Z]{2,}` 正则匹配覆盖，
  但解决之道是预防而非修复——禁止 LLM 生成它们
- 已入库的旧总结不受影响；如需重新生成，使用 `reset-summary --all`

# 2026-06-04 — SKIP 覆盖隔离与 Email 配置合并到 .env

## SKIP 覆盖隔离

**背景**：Web UI Config 页面切换的 SKIP 状态持久化到 `data/skip_overrides.json`，但该文件被
`runner.py` 无条件加载（`overrides = _load_skip_overrides()`），导致 Web UI 的设置意外影响 CLI 行为。
Web UI Pipeline 页面使用 `force=True` 本来就忽略 SKIP 配置，等于"Web UI 写了一个只影响 CLI 的配置"，
违反直觉。

**解决**（`src/pipeline/runner.py`）：
- `overrides = _load_skip_overrides()` → `overrides = _load_skip_overrides() if force else {}`
- CLI（`force=False`）只使用 `config.py` 原生 `SKIP_PHASE_*` 值
- Web UI 的 `force=True` 路径不受影响

## Email 配置合并到 .env

**背景**：SMTP 配置（含密码凭证）分散在 `configs/email.yaml` 中，与 `.env` 中的 API 密钥同属敏感信息
却分两处管理。`email.yaml` 虽然被 `.gitignore` 排除，但额外的 yaml 文件增加了用户的认知负担。

**解决**：
- `configs/email.yaml` — 完全删除（原已 gitignore，不影响已有本地配置）
- `configs/email.yaml.example` — 删除（不再需要）
- `.env` / `.env.example` — 新增 7 个 `SMTP_*` 字段（host/port/use_tls/username/password/from_addr/to_addrs），`to_addrs` 用逗号分隔
- `src/config.py` — `load_email_config()` 从 `os.getenv` 读取，拼装与原 `email.yaml` 相同结构的 dict（`phase_h.py` 零改动）
- `tests/real/real_email.py` — 改为调用 `config.load_email_config()`，不再直接读 yaml
- `.gitignore` — 移除 `configs/email.yaml` 行
- 更新 docs/README.md、docs/design.md 中相关引用

**不受影响**：`EmailSender` 构造函数、`phase_h.py`、`web/app.py`、`configs/publishers.yaml` / `keywords.yaml`。

# 2026-06-04 — Phase D 重构：参考排序模式 + 模型升级 + 子领域分离

**背景**：原 Phase D 作为 Phase E 的门禁，用 sentence-transformers 余弦相似度阈值（0.3）过滤论文。
实践中发现：(1) `all-MiniLM-L6-v2` 的 256 token 上限导致长 `domain_description` 被截断；(2) 单向量
编码三个不同子领域信息被稀释；(3) 每轮 ~200-400 篇论文的 LLM API 成本仅 ~$0.08，阈值过滤的节省微不足道。

**核心变更**：Phase D 从"门禁"改为"参考排序"，与 Phase E 解耦。

### 变更详解

**1. 子领域分离**（`configs/keywords.yaml`）

新增 `sub_domains` 字段，将 `domain_description` 的三段拆为独立子领域：
- `ion_acceleration` — 激光离子加速
- `beam_transport` — 等离子体束流传输
- `control_system` — 加速器控制系统

| 字段 | 用途 | 语种 | 要求 |
|------|------|------|------|
| `domain_description`（保留） | Phase E LLM prompt | 中/英均可 | 尽量详细 |
| `sub_domains`（新增） | Phase D 语义相似度 | **仅英文** | 每段 < 300 字，简练自然语言 |

`domain_description` 与 `sub_domains` 的关系：前者是给 LLM 看的完整领域描述；后者是从中提取核心语义
的英文简练段落，专供嵌入模型编码。

**2. 模型升级**（`src/config.py`）

`all-MiniLM-L6-v2` (256 tokens, 384-dim) → `BAAI/bge-base-en-v1.5` (512 tokens, 768-dim)

消除长摘要被截断的风险（大部分 title + abstract ≤ 450 tokens）。

**3. 解耦 Phase D 与 Phase E**（`src/pipeline/phase_d.py`）

| 行为 | 旧 | 新 |
|------|----|----|
| Phase D 修改 `llm_relevance_status` | 分数 < 0.3 时标记 `skipped` | **不移除** — 所有论文正常进 Phase E |
| Phase D 用途 | 门禁过滤 | 仅计算参考分数供排序 |
| `SKIP_PHASE_D` 默认值 | `False` | **`True`**（跳过，全部走 LLM） |
| `SEMANTIC_SIMILARITY_THRESHOLD` | `0.3` | **已删除**（不再需要） |
| `compute_similarity()` 返回值 | `float` | `tuple[float, str\|None]` — 分数 + 最佳子领域标签 |

**4. SemanticFilter 多向量支持**（`src/processors/paper_relevance.py`）

```python
# 旧
sf = SemanticFilter(model_name, "单一段落描述")
score = sf.compute_similarity(title, abstract)

# 新
sf = SemanticFilter(model_name, {"label1": "段落1", "label2": "段落2"})
score, best_label = sf.compute_similarity(title, abstract)
```

每条子领域预编码为独立向量，取余弦相似度最高者作为总分并记录子领域标签。

**5. WebUI Papers 页适配**（`src/web/templates/papers.html` + `src/web/app.py`）

| 场景 | 显示 |
|------|------|
| Phase D 关闭（默认） | 无分数列，按日期降序排列 |
| Phase D 开启 | 有分数条 + 最佳子领域标签，分数列优先 |
| 混合数据 | ORDER BY 使用 `semantic_similarity_score IS NOT NULL DESC, score DESC, date DESC` |

Reset 定义修正：

```python
# 旧
"RESET_DEFS["D"]" → 含 llm_relevance_status + llm_relevance_result
"RESET_CASCADE["D"]" → "llm_relevance_status"

# 新
RESET_DEFS["D"] → 仅含 semantic_filter_* + semantic_similarity_score + semantic_best_subdomain
RESET_CASCADE["D"] → ""  # 空，不级联
```

**6. `tools/reset_pipeline.py` SEMANTIC_CASCADE 精简**

从 13 行（语义 + LLM + 报告）缩减为 5 行（仅语义相关列）：
```
semantic_similarity_score = NULL
semantic_filter_status = 'pending'
semantic_filter_error = NULL
semantic_filter_date = NULL
semantic_best_subdomain = NULL
```

**7. DB Schema**（`src/db/database.py`）

| 列名 | 类型 | 用途 |
|------|------|------|
| `semantic_best_subdomain` | TEXT (新增) | 最佳匹配子领域标签 |

`get_papers_sorted_by_semantic()` 改为全量返回（无 WHERE score IS NOT NULL 限制），
ORDER BY 增加回退排序。

### 文件改动清单

| 文件 | 变更概要 |
|------|---------|
| `configs/keywords.yaml` | 新增 `sub_domains` 字段（3 子领域） |
| `src/config.py` | 模型路径 bge-base-en-v1.5；`SKIP_PHASE_D=True`；删除阈值；`load_keywords()` 返回 `sub_domains` |
| `src/processors/paper_relevance.py` | `SemanticFilter` 多向量支持，`compute_similarity()` 返回 `(score, best_label)` |
| `src/db/database.py` | 新增 `semantic_best_subdomain` 列 + 迁移；`update_semantic_filter()` 加 `best_subdomain` 参数；`get_papers_sorted_by_semantic()` 全量返回 + 回退排序 |
| `src/pipeline/phase_d.py` | 重写：去掉阈值、去掉 llm_relevance 级联、使用 sub_domains 多向量 |
| `src/web/app.py` | `RESET_DEFS["D"]` 只重置语义列；`RESET_CASCADE["D"]=""`；`_execute_reset`/`_count_reset_impact` 处理非状态列 |
| `src/web/templates/papers.html` | None 分数自适应 + 子领域列 |
| `tools/reset_pipeline.py` | `SEMANTIC_CASCADE` 精简为仅语义列；help 文本更新 |
| `tests/test_relevance.py` | SemanticFilter 测试适配新接口 + 多子领域 fixture |

### 遗留

- `Phase C NonResearchPageError` 级联机制保留不变（非论文页面仍应跳过所有下游处理）
- `tools/reset_empty_abstract.py` 仍重置 Phase D/E/G，无影响（语义分可重新计算）

# 2026-06-04 — 双源发现：RSS + CrossRef 并行 + 来源标注

**动机**：
1. RSS 的完整性不可控——Feed 只返回最新 N 篇或编辑精选，无法确认是否有遗漏
2. 时间跨度受限——RSS 天然只提供最近内容，无法回溯或补漏
3. 调试困难——无法区分论文从哪个数据源发现，难以判断 RSS 是否"缺斤少两"

**解决**：

### 架构变革

Phase A 从单一路径（RSS）拆为**双路径并行**：

```
Phase A (新版)
  ├─ A-RSS:  RSS Feed 抓取 ← 原有逻辑
  └─ A-CR:   CrossRef 期刊查询 ← 新增
```

两路各有独立 SKIP 开关（`SKIP_PHASE_A_RSS` / `SKIP_PHASE_A_CR`），在 Web UI Pipeline 页面也显示为两个独立按钮。

### 新增：`CrossrefClient.fetch_by_journal()`

`src/sources/crossref.py` 新增方法，用于按 ISSN + 日期范围批量获取期刊论文列表：

| 端点 | `GET /journals/{issn}/works` |
|------|------------------------------|
| 过滤 | `type:journal-article`（排除 editorial/correction）|
| 翻页 | offset 模式，最大 100 条/页，上限约 10000 条 |
| 限流 | 页间 0.2s 礼貌间隔 |
| 返回 | `list[PaperMetadata]`（doi/title/date/journal/publisher/authors/url 等） |

### 新增：来源标注列 `discovery_source`

**数据库**（`src/db/database.py`）：
- 新增 `discovery_source TEXT` 列，存储论文的发现来源

| 值 | 含义 |
|----|------|
| `rss` | 仅 RSS 发现 |
| `crossref` | 仅 CrossRef 发现 |
| `rss,crossref` | 两路都发现了这篇 |

- `insert_paper_basicinfo(doi, ..., source)` — 通用插入方法，新论文写入发现来源
- `append_discovery_source(doi, source)` — 已有论文追加新来源（逗号分隔，不重复）
- `insert_rss_basicinfo()` — 兼容旧接口，自动设置 `discovery_source='rss'`

**调试用法**：
```sql
SELECT discovery_source, COUNT(*) FROM papers GROUP BY discovery_source;
```
输出样例：
```
rss              →  142  (仅 RSS 发现)
crossref         →   35  (仅 CrossRef 发现，RSS 漏了这些)
rss,crossref     →  223  (双路均发现)
```
如果 `crossref_only` 数量大于 0，说明 RSS 确实存在遗漏。

### 配置变动

**`configs/publishers.yaml`** — 22 个期刊各新增 `issn` 字段：

```yaml
- id: nature
  name: Nature
  publisher: nature
  rss: https://www.nature.com/nature.rss
  issn: "1476-4687"        # 新增
  enabled: true
```

**`src/config.py`** — 新增配置项：

```python
SKIP_PHASE_A_RSS = False    # RSS 发现路径
SKIP_PHASE_A_CR = False     # CrossRef 发现路径
CROSSREF_LOOKBACK_DAYS = 1  # 每日增量回溯天数
```

### Phase A 详细逻辑

**A-RSS**（`phase_a_rss`）— 与原来一致，仅增加 `discovery_source='rss'` 写入。

**A-CR**（`phase_a_crossref`）：
1. 计算时间窗口：`from = today - CROSSREF_LOOKBACK_DAYS`，`to = today`
2. 遍历每个 enabled + 有 ISSN 的期刊
3. 调用 `fetch_by_journal(issn, from_date, to_date)`
4. 对每个返回的论文：
   - DOI 不存在 → `insert_paper_basicinfo(..., source='crossref')`
   - DOI 已存在（已被 RSS 发现）→ `append_discovery_source(doi, 'crossref')`

### 文件改动清单

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `configs/publishers.yaml` | ~20 行 | 22 个期刊各加 `issn` |
| `src/config.py` | ~10 行 | 新增 `SKIP_PHASE_A_RSS` / `SKIP_PHASE_A_CR` / `CROSSREF_LOOKBACK_DAYS` |
| `src/sources/crossref.py` | ~80 行 | 新增 `fetch_by_journal()` |
| `src/db/database.py` | ~60 行 | 新增 `discovery_source` 列 + migration + `insert_paper_basicinfo()` + `append_discovery_source()` |
| `src/pipeline/phase_a.py` | ~80 行 | 新增 `phase_a_crossref()`；`phase_a_rss()` 守卫改为 `SKIP_PHASE_A_RSS` |
| `src/pipeline/runner.py` | ~10 行 | Phase map 新增 A-RSS / A-CR |
| `src/web/app.py` | ~5 行 | `PHASE_LABELS` / `PHASE_DEFAULTS` 拆分为 A-RSS / A-CR |
| `src/web/templates/pipeline.html` | 2 行 | Reset 按钮排除 A-RSS / A-CR |
| `tests/test_crossref.py` | ~100 行 | 3 个 `fetch_by_journal` 新测试（basic/pagination/max_results）|
| `tests/test_phases.py` | ~15 行 | 新增 `test_phase_a_crossref_signature` |

**测试结果**：`pytest tests/` → **92 passed**（含 3 个新增 crossref 测试）

# 2026-06-04 — Web UI 定位重构 + 配置隔离 + 新页面

**背景**：Web UI 是临时起意开发的，缺乏明确定位。功能散乱，SKIP 切换语义混乱（Config 页切换影响 CLI 而非 Web UI）。

**核心决策**：明确定位 Web UI = "Pipeline 监控仪表盘 + 报告工作站"，不是 CLI 替代品。

### 配置隔离

```
之前: skip_overrides.json → runner.py 无条件加载 → 影响 CLI + Web UI（但 force=True 绕过）
之后: skip_overrides.json → runner.py 仅 force=True 时加载 → 仅影响 Web UI
      CLI → 只读 config.py 的 SKIP_PHASE_* → 不受 Web UI 影响
```

### 变更详解

**1. SKIP 切换语义修正**（`src/pipeline/runner.py`）

| 行为 | 改前 | 改后 |
|------|------|------|
| `force=True` 绕过 SKIP 检查 | 是（line 102: `if not force and not enabled`） | 否（改为 `if not enabled`） |
| Config 页 SKIP 切换效果 | 仅影响 CLI（隔离前）/ 无效果（隔离后） | 影响 Web UI Pipeline 页按钮状态 |
| CLI 是否受 overrides 影响 | 是（force=False 时不加载 overrides ✅，但之前版本会） | 否（完全不读取 skip_overrides.json） |

**2. Pipeline 页跳过阶段交互**

- Config 页切换 Phase E → Skip → 写入 `skip_overrides.json`
- Pipeline 页每 10s 轮询 status API → 拿到 `effective_skip`
- Phase E 按钮 → 灰显 + 文字变为"(Skipped)" + 不可点击
- 直接 POST `/pipeline/run/E` → 后端返回 400: "Phase E is skipped in Config"
- Run All → 自动跳过被跳过的阶段
- 三层防护：前端禁用 → API 守卫 → runner 跳过

**3. Papers 页排序改造**

| 维度 | 改前 | 改后 |
|------|------|------|
| 默认排序 | 语义相似度（Phase D 关闭时回退日期） | 入库日期（`created_date DESC`） |
| 可选排序 | 无 | 发表日期（`COALESCE page > crossref > rss`，含精度警告） |
| 展示列 | 语义分 + 子领域 | 语义分（可选）+ LLM 相关性状态 ✓/✗ + 日期 |

**4. 新增 Data Sources 页面**

独立配置偏好文件 `data/journal_overrides.json`：

```json
{
  "journals": {
    "nature": { "enabled": true, "rss_enabled": true, "cr_enabled": true },
    "nphys": { "enabled": false }
  }
}
```

- `phase_a.py` 新增 `_load_journal_overrides()` / `_journal_effective()`
- 不修改 `publishers.yaml`（安全的独立覆写）
- 每个期刊可独立控制 RSS 和 CrossRef 数据源

**5. Config 页增强**

| 组件 | 实现 |
|------|------|
| Domain description 文本框 | 读取/写入 `keywords.yaml` 的 `domain_description` 字段 |
| MinerU Token 色标 | 解码 JWT `exp` 字段：绿 >30d / 黄 7-30d / 红 <7d |
| 连通性测试按钮 | 3 个按钮：DeepSeek（ping 请求）/ CrossRef（查已知 DOI）/ MinerU（user/info 端点） |

### ruamel.yaml 保留 YAML 注释

**问题**：`config/save-domain` 使用 `yaml.safe_load()` + `yaml.dump()` 写回 `keywords.yaml`，`dump()` 不保留文件中的注释行（`# sub_domains: ...`、`# General & Core Concepts` 等全部丢失）。

**解决**：改用 `ruamel.yaml` 替代 `pyyaml` 的 dump：

```python
# 改前
kw = yaml.safe_load(path.read_text())
kw["domain_description"] = content
path.write_text(yaml.dump(kw, ...))

# 改后
from ruamel.yaml import YAML
ryaml = YAML()
kw = ryaml.load(path)        # 保留注释的 CommentedMap
kw["domain_description"] = content
ryaml.dump(kw, path)         # 写回，注释完好
```

注：`config/save-publishers` / `config/save-keywords` 是全文替换（浏览器 textarea → 原文写回），不受此问题影响。

### 文件改动清单

| 文件 | 改动 |
|------|------|
| `src/web/app.py` | `config/save-domain` 改用 `ruamel.yaml.YAML().load/dump` 保留注释 |
| `docs/README.md` | 安装命令增加 `ruamel.yaml` |
| `docs/tasks.md` | 本文 |
| `src/pipeline/runner.py` | force 语义修正：`if not enabled` 取代 `if not force and not enabled` |
| `src/pipeline/phase_a.py` | 新增 `_load_journal_overrides()` / `_journal_effective()`；A-RSS/A-CR 读取 journal_overrides.json |
| `src/web/app.py` | 新增 datasources / datasources/save / config/mineru-token / config/test-* / config/save-domain 端点；`_pipeline_status()` 增加 `effective_skip`；`run_phase()` 增加跳过守卫 |
| `src/web/templates/pipeline.html` | 新增 `updatePhaseButtons()` 处理跳过按钮状态 |
| `src/web/templates/papers.html` | 完全重写：排序选择 + 语义分列 + LLM 相关性列 + 日期列 + 精度警告 |
| `src/web/templates/datasources.html` | **新建**：期刊启用表格 + RSS/CrossRef 独立开关 + 联动逻辑 |
| `src/web/templates/config.html` | 新增 domain 文本框 + 连通性测试 + MinerU Token 状态 |
| `src/web/templates/base.html` | 侧边栏新增 Data Sources 入口 |
| `src/web/templates/home.html` | 新增 Data Sources 快速指南行；更新 SKIP 描述 |
| `src/web/static/js/app.js` | 新增 datasources / config 相关的 i18n 键（中英文共 ~40 个） |
| `src/web/static/css/style.css` | 新增 `.btn-disabled` / `.td-center` / `.alert` / `.conn-test-*` 样式 |
| `src/db/database.py` | 新增 `get_papers()` 方法支持 created/published 排序 |
| `docs/design.md` | Web UI 定位章节 + 配置隔离规则 + 页面表更新 |
| `docs/tasks.md` | 本文 |

# 2026-06-05 — AIP PDF 下载回退链演进（两条失败方案）

**背景**：AIP 的 PDF URL 是直接下载链接（`wget` 可下），但 `page.evaluate(fetch)` 被 CSP 拦截。
当时假设「同域 = fetch 可用」被证伪——同域但 CSP `connect-src` 可单独封锁 JS API。

## v1 尝试（已弃用）：`page.goto(pdf_url) + response.body()`

**思路**：浏览器原生导航不受 CSP 限制，`goto()` 返回的 response 应包含 PDF 字节。

**失败原因**：浏览器以 stream 方式消费 PDF 响应体，将 PDF 流入内置 PDF viewer，
`response.body()` 返回 None（body 已被消费完）。这是 Playwright 对 PDF URL 的处理特性，
非 HTTP 层问题。

**教训**：`page.goto(pdf_url)` 的 `response.body()` 对 PDF 不可靠——不等 body 缓冲就消费了。
这和 `page.on("response")` 监听器中的 `response.body()` 不同——监听器在网络事件分发的
时间窗口内 body 尚未被消费，而 `goto()` 返回时 PDF 已被 viewer 接受。

## v2 尝试（已弃用）：`<a click> + page.expect_download()`

**思路**：创建 `<a download>` 元素并 `click()`，模拟用户点击触发浏览器下载事件。

**失败原因**：AIP 不认程序化 `element.click()` 为「用户手势」，浏览器不触发下载事件，
`expect_download` 60s 超时。JS 的 `.click()` 是合成事件（`isTrusted=false`），
部分网站的 JS 逻辑会检查 `event.isTrusted` 并忽略合成事件。

**教训**：程序化 `<a>.click()` ≠ 真实用户点击。浏览器安全机制通过 `event.isTrusted`
区分合成事件和真实交互，部分 publisher 前端据此过滤。

## 最终方案：`requests` + 浏览器 cookies + User-Agent

**方案**：从浏览器 context 提取 cookies 和 `navigator.userAgent` → Python `requests` 直连下载。

**为什么可行**：
- AIP 的安全模型是「浏览器 JS 层 CSP + 用户手势检测」
- PDF URL 在 HTTP 层完全无校验（`wget` 可直接下载）
- 纯 HTTP 请求绕过 CSP、用户手势、TLS 指纹等所有浏览器层防御
- 提取的 cookies 携带浏览器 session，User-Agent 和 Referer 使请求在 HTTP 层与浏览器导航无异

**代码位置**：`src/sources/publisher.py:download_pdf()`

**最终三级回退链**：
```
page.evaluate(fetch)                → 主路径，Nature/Science/APS/Cambridge/IOP
    ↓ CSP 拦截 (AIP)
requests + 浏览器 cookie/UA/Referer → HTTP 层，绕过所有 JS 层限制
    ↓ 失败
RuntimeError                        → 标记 failed（再无登录或更深层问题）
```

# 2026-06-05 — `page.on("response")` 监听器被移除的教训

**原始设计**（v2，2026-05-24）：
```
page.on("response") 监听 → 捕获浏览器网络层 PDF 响应（主路径）
page.evaluate(fetch) → 兜底
```

**被移除**（v4，2026-06-01，Playwright→cloakbrowser 重构）：
理由：「不依赖 response 监听 — 目前版本无需 page.on("response")，
因为同域 fetch 足以覆盖所有 publisher」。

实际原因：从 `main.py`（1310 行）搬入 `publisher.py` 时简化了代码。
原 `main.py` 中 Phase E2 的 PDF 下载是三层方案（response 监听主路径 → fetch 兜底 → failed），
搬入 `download_pdf()` 时只保留了 fetch 层，删除了 response 监听。

**该假设被 AIP 打破**：同域但 CSP `connect-src` 单独拦截 fetch()。

**教训总结**：
1. 同源策略（SOP）和内容安全策略（CSP）是两个独立的浏览器安全层——
   SOP 管跨域请求，CSP 管任意 JS API 调用路径。同域 ≠ JS fetch 可用。
2. `response.body()` 在 `page.goto(pdf_url)` 时不可靠（PDF viewer stream 消费），
   但在 `page.on("response")` 监听器中可靠——监听器在 body 被消费前拿到数据。
3. 代码简化不应以丢失回退路径为代价。三层方案（主路径 → 兜底 → failed）应始终保留。
4. 不同 publisher 的网络层行为差异巨大——CSP 策略、用户手势检测、WAF 级别各不相同。
   单一下载机制无法覆盖所有场景。

# 2026-06-06 — Review Bug 修复

**背景**：`docs/reviews/2026-06-06-review-suggestions.md` 提交了项目架构与代码审查报告，
包含 5 个优先级较高的 Bug 和安全隐患。

**修复清单**：

| # | 问题 | 优先级 | 文件 | 修复 |
|---|------|--------|------|------|
| 1 | `config_save_prompt` 缺少 `request` 参数 | P0 🔴 | `src/web/app.py` | 函数签名添加 `request: Request` 参数 |
| 2 | `fix_json_invalid_escapes` 双重调用 | P0 🔴 | `src/pipeline/phase_e.py`, `phase_f.py` | 移除 Phase E/F 中的二次修复调用；删除 `from common import fix_json_invalid_escapes` |
| 3 | Phase E2 PDF 下载无代理 | P1 🟡 | `src/pipeline/phase_e2.py` | 按 publisher 分组，对 SCRAPER_MAP 中存在的 publisher 使用 `create_scraper(publisher)` 创建浏览器实例（含代理）；其余回退 BasePublisherScraper |
| 4 | DOI 路径穿越 | P2 🟡 | `src/pipeline/phase_e2.py` | `safe_doi` 清洗增加 `.replace("..", "_")` |
| 5 | Phase B 重复代码分支 | P2 🟢 | `src/pipeline/phase_b.py` | 提取通用 DB 更新到 if/else 外部，`if` 分支仅保留 warning 日志 |

**测试结果**：`pytest tests/` → **99 passed**（保持不变）

# 2026-06-07 — PDF 下载重构：顺序反转 + APS 导航容错

**背景**：`download_pdf()` 长期以来的下载顺序是 JS fetch 主路径 → requests+cookie 回退。
AIP 出版社的 CSP（Content Security Policy）拦截了浏览器的 `fetch()` API，每次下载都要
等待 60s 超时才降级到 requests。同时，APS 的 `link.aps.org` → `journals.aps.org` 302 重定向
偶发在执行 `page.evaluate()` 导航后二次跳转，导致 `Execution context was destroyed` 崩溃。

## 3 处核心改动

| # | 位置 | 改前 | 改后 |
|---|------|------|------|
| ① | `goto` 后等待 | `wait_for_timeout(5000)` | **`wait_for_timeout(15000)`** — 给 APS 二次导航多留稳定时间 |
| ② | 同域 PDF 链接提取 | 裸 `page.evaluate()`，导航导致上下文销毁即崩溃 | **`for _attempt in range(2)` + try/except + 3s 重试** — 导航不稳定时自动恢复 |
| ③ | 下载优先级 | **JS fetch（主）** → requests+cookie（回退） | **requests+cookie（主）** → JS fetch（兜底） |

## 下载数据流对比

```
改前:
  goto + wait 5s → DOM 查 PDF 链接（裸调用）→ JS fetch（主, 60s 超时）→ requests+cookie（回退）

  问题:
  - AIP: JS fetch 被 CSP 拦截，等 60s 才回退 → 白等
  - APS: navigate 不稳定 → DOM 查询崩 → pdf_url 未替换 → 跨域 fetch 也崩

改后:
  goto + wait 15s → DOM 查 PDF 链接（try/retry）→ requests+cookie（主, 秒级失败）→ JS fetch（兜底）

  优势:
  - AIP: requests 绕过了 CSP，秒级返回
  - APS: 15s 稳定窗口 + try/retry → 同域链接可靠提取 → requests + cookie 直下
```

## 设计考量

### requests+cookie 为什么能覆盖所有 publisher

`download_pdf()` 在提取同域 PDF 链接成功后，`pdf_url` 已被替换为当前页面**同域**的 URL
（如 `journals.aps.org/prresearch/pdf/XXX`）。同域下 requests + 浏览器 cookie 发送
HTTP 请求，不存在 CORS/CSP 问题。对于 Nature/Science/Cambridge/IOP/Optica 等 publisher，
`citation_pdf_url` 本身就在同域，同样适用。

JS fetch 保留为兜底，假设未来某个 publisher 的 PDF 需要完整的浏览器 JS 执行环境才能下载。

### UA 降级保护

`self.page.evaluate("navigator.userAgent")` 同样可能因导航销毁上下文而失败，
改为 try/except + 硬编码 Chrome 120 UA 字符串兜底：

```python
try:
    ua = self.page.evaluate("navigator.userAgent")
except Exception:
    ua = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
```

### 三层防护与兜底（APS 导航容错）

APS 使用 `link.aps.org` → `journals.aps.org` 双域名架构，goto 后的二次导航可能
在任何时刻销毁执行上下文。`download_pdf()` 的三层防护：

| 层 | 防护 | 失效时 |
|----|------|--------|
| 1 | `wait_for_timeout(15000)` 等待充分稳定 | 进入第 2 层 |
| 2 | `for _attempt in range(2)` + except 重试 | 保留原始 `pdf_url`（跨域） |
| 3 | requests+cookie 全局兜底（第 2 层已非核心） | JS fetch 兜底（第 2 层失败时跨域 fetch 也可能失败） |

# 2026-06-07 — 6GB 内存问题定位与修复

**背景**：运行 `python src/main.py` 时进程占用 6GB 内存，远超预期。经分析发现为 Chromium 子进程泄露。

**根因**：cloakbrowser 的 `context.close()` 虽包装了 `pw.stop()`，但 `pw.stop()` 仅断开 WebSocket 连接，**不保证 Chromium 子进程退出**。Phase C 按 publisher 分组顺序处理 7 个 publisher，每个启动一个 Chromium（~300MB），`close()` 后进程变成孤儿继续吃内存，累计 2GB+。加上 sentence-transformers 模型（~1.5GB）、Python 数据结构和 Phase E2 额外浏览器启动，达到 6GB。

**修复**（`src/sources/publisher.py` `BasePublisherScraper.close()`）：
- 在 `context.close()` 前显式调用 `browser = self.context.browser; browser.close()` 杀 Chromium 进程
- 更新 docstring 说明原因

# 2026-06-06 — Accepted Paper 生命周期修正：删除而非跳过

**背景**：APS 在正式发表前会发布 Accepted Paper 版本（URL 含 `/accepted/`）。
这些论文后续会以正式论文形式发表，且 **DOI 保持不变**。旧方案将其标记为
`skipped` 并 cascade skip 下游阶段，导致：
1. 论文永久 stuck 在 DB 中（`paper_doi_exists()` 返回 True 阻止重新发现）
2. 正式发表后流水线无法重新获取和处理
3. 66 篇同类论文累积在数据库中

**解决**：检测到 Accepted Paper 时直接从 DB 删除，而非标记跳过。

### 改前 vs 改后

```
改前: 发现 Accepted Paper → mark skipped → cascade skip D/E → 论文永久 stuck
改后: 发现 Accepted Paper → DELETE FROM papers → Phase A 重新发现 → 正式论文正常处理
```

### DB 层 — `src/db/database.py`
新增 `delete_paper(doi)` 方法。

### Pipeline 层 — `src/pipeline/phase_c.py`
`AcceptedPaperError` 处理逻辑从 6 行 `update_*` cascade skip 替换为单行 `db.delete_paper(paperDOI)`。

### 工具层 — `tools/delete_accepted_papers.py`
清理存量数据脚本，扫描 `publisher_page_fetched_error LIKE 'AcceptedPaper:%'`：
```bash
python tools/delete_accepted_papers.py --dry-run   # 预览（不删除）
python tools/delete_accepted_papers.py              # 交互确认
python tools/delete_accepted_papers.py --force       # 跳过确认
```

### 设计决策

| 决策 | 理由 |
|------|------|
| **删除而非跳过** | Accepted Paper 的 DOI 与正式版相同，保留则永久阻塞重新发现 |
| **不影响 NonResearchPageError** | Erratum / Comment 等永远不会变成正式论文，保留原有跳过逻辑 |
| **不在 Phase A-CR 阶段过滤** | CrossRef API 不提供 "accepted" vs "published" 标记，唯一可靠检测在 Phase C |
| **删除时机足够安全** | 论文必须先通过 A-CR 插入（有 DOI），再经 Phase C 访问页面确认——两阶段确认无误 |

### 清理结果

首次执行删除存量 66 篇 Accepted Paper（全部为 APS 期刊的非课题组方向论文），
清理后 `pytest tests/` → **99 passed**（不变）。

# 2026-06-07 — Optica 反爬检测：非 CF 拦截的正文缺失识别

**背景**：Optica 的反爬机制不同于 Cloudflare Challenge——它不会返回 `challenge-platform`、
`cf-browser-requification` 等 CF 特征关键词，也不会完全拒绝请求。而是返回一个**部分页面**：
`<head>` 中的 `<meta>` 标签正常加载（title/DOI 可提取），但正文内容（`#articleBody` div）被拦截。

## 问题链路

```
Optica 反爬返回:
  <head>
    <meta name="citation_title" content="...">  → parse_page 提取到 title ✓
    <meta name="citation_doi" content="...">     → parse_page 提取到 doi ✓
  </head>
  <body> [空白/验证页]                          → #articleBody 不存在

Phase C 检测链:
  CF 检测      → 关键词全不命中 → 通过
  三空检查     → title+doi 有值 → 通过
  非论文关键词  → 标题不含 erratum 等 → 通过
  → 标记为 success ← 空 abstract
```

## 修复

**`OpticaScraper.parse_page()` 新增正文结构检测**：

```python
if title and not abstract:
    if not sel.xpath('//div[@id="articleBody"]'):
        raise PageParseError(
            "Optica anti-bot blocked: article body (#articleBody) not found"
        )
```

这样在 abstract 为空但 `#articleBody` 也不存在时，直接抛出 `PageParseError`，
Phase C 将其捕获后走重试/失败逻辑，不再误标 success。

## 配套工具更新

`tools/reset_empty_abstract.py` 扩展重置范围：

| 列 | 改前 | 改后 |
|----|------|------|
| `publisher_page_fetched_*` | 不变 | **重置为 pending** |
| `semantic_filter_*` | 重置 | 重置（不变） |
| `llm_relevance_*` | 重置 | 重置（不变） |
| `report_*` | 重置 | 重置（不变） |

之前只重置 Phase D/E/G，现在加入 Phase C，使得空 abstract 论文可以触发重新抓取。

# 2026-06-10 — 四项改进：非论文页删除、日志轮转、邮件模板、自动重试

## 1. 非论文页面直接删除

**动机**：NonResearchPageError 之前做 cascade skip（标记 skipped + 级联下游），但非论文页面

永远不可能变"相关"，留在数据库中只会占据空间、增加查询噪音。AcceptedPaperError 已经用 delete_paper()
直接删除，NonResearchPageError 也应一致。

**变更**（`src/pipeline/phase_c.py`）：

之前 cascade skip 逻辑（约 14 行）：
```
except NonResearchPageError:
    consecutive_failures = 0
    update_error_message(...)        # publisher_page_fetched → skipped
    update_process_status(...)       # semantic_filter_status → skipped
    update_process_status(...)       # llm_relevance_status → skipped
    paper_skipped = True
```

改为 5 行：
```
except NonResearchPageError:
    consecutive_failures = 0
    db.delete_paper(paperDOI)
    logger.info(f"Non-research page deleted: {paperDOI}")
    paper_skipped = True
```

## 2. 日志轮转（RotatingFileHandler）

**动机**：`FileHandler` 不轮转，长期运行后 `data/PaperCrawler.log` 持续增长，
可能耗尽磁盘空间。WebUI Logs 页面读取整个文件也变慢。

**变更**：3 个入口点统一替换。
| 文件 | 改前 | 改后 |
|------|------|------|
| `src/main.py` | `logging.FileHandler` | `RotatingFileHandler(10MB, backupCount=5)` |
| `tools/schedule_daily.py` | 同上 | 同上 |
| `tools/schedule_weekly.py` | 同上 | 同上 |

## 3. 邮件 HTML 模板

**动机**：Phase H 发送纯文本邮件，无格式、无品牌。HTML 邮件能提供更好的阅读体验。

### 模板设计（已确认的最终方案）

**模板文件**：`templates/email/default.html`
- 使用 `str.format()` 替换，不引入 Jinja2 等新依赖
- 模板变量：`{report_title}`、`{paper_msg}`、`{attachment_section}`、`{journal_list}`、`{keyword_list}`、`{domain_block}`、`{publisher_stats}`、`{threshold}`
- 报告文件作为附件发送，正文无论文列表（通过邮件直接分享报告，避免正文过长）
- 一个固定模板（详细版 vs 简化版的差异在只有 3 个字段时过于微小，不分开）
- Footer: 无运行时信息（不暴露服务器路径、版本号等）

### 相关变更

| 文件 | 变更 |
|------|------|
| `templates/email/default.html` | **新建**。HTML 邮件模板，蓝色 header + 正文 + 附件提示 + 灰色 footer |
| `configs/settings.yaml` | 新增 `email.template: "default"` 配置项 |
| `src/config.py` | 新增 `EMAIL_TEMPLATE_DIR`、`EMAIL_TEMPLATE_NAME`、`EMAIL_TEMPLATE_DEFAULT`；支持 `email_template_override.txt` 覆盖 |
| `src/pipeline/phase_h.py` | 新增 `_render_email_template()` 工具函数；`phase_h_email` 改用 HTML 渲染 + `body_type="html"` |
| `src/web/app.py` | 新增 `POST /config/save-email-template` 端点 |
| `src/web/templates/config.html` | 新增 Email Template 文本输入框 + 保存按钮 |

## 4. 自动重试

**动机**：Phase C 的 Publisher 抓取可能偶发失败（Cloudflare 瞬态拦截、网络抖动），
失败论文留在 `failed` 状态，需要用户手动跑 `reset-publisher` 才能重试。
每日调度脚本应在运行前自动重置失败状态。

**变更**（`tools/schedule_daily.py`）：

```python
# 在 run_daily() 之前添加：
reset_db = DatabaseClient(DB_PATH)
reset_db.init_db_papers()
count = reset_db.batch_reset_status(
    [("publisher_page_fetched_status", "pending")],
    "publisher_page_fetched_status = 'failed'",
)
if count:
    logger.info(f"Auto-reset {count} failed publisher pages for retry")
```

**设计考量**：
- 不重置 `skipped` 状态（非论文页面、禁用 publisher 等有意义的状态不应被覆盖）
- 不重置 Phase D/E2/F/G/H 的状态（只有 Publisher 抓取需要自动重试）
- 只影响 `schedule_daily.py`，不影响 `main.py` 全流程（全流程手动跑，用户可自行决定）
- 简单一行操作，不需要复杂的状态机或计数逻辑

## HTTP Fallback 机制（Nature + IOP, 2026-06-14）

### 背景
- **Nature**: Fastly Client Challenge 拦截所有自动化浏览器，但 `wget` 可正常获取 HTML → 浏览器问题，非 HTTP 层封锁
- **IOP**: 大部分文章浏览器可获取，但极个别文章被拦截（wget 也被拦 → 有 TLS 指纹检测）

### 方案
在 `BasePublisherScraper` 中增加两阶段 HTTP fallback 机制：

**类属性配置**：
- `http_fallback_mode`: `None` / `"requests"` / `"curl_cffi"`
- `http_fallback_strategy`: `"primary"`（先 HTTP，失败走浏览器） / `"fallback"`（先浏览器，检测到拦截页后回退 HTTP）

**赋值**：
- `NatureScraper`: `http_fallback_mode = "requests"`, `http_fallback_strategy = "primary"`
- `IOPScraper`: `http_fallback_mode = "curl_cffi"`, `http_fallback_strategy = "fallback"`

**`_http_fetch(url, timeout_sec)`**：
- `"requests"` 模式: `requests.get()` + 浏览器 UA/Headers
- `"curl_cffi"` 模式: `curl_cffi.requests.get(impersonate="chrome")`（TLS 指纹伪造）

**`_is_bot_page(html, title)`**：
检测标题中 "Client Challenge"、"Just a moment" 等关键词，或 HTML 中的 CF/Captcha 标记。

**`fetch_page()` 改动**：
- "primary" 策略：先调 `_http_fetch()`，成功则跳过浏览器导航
- "fallback" 策略：浏览器导航失败或拿到拦截页后，自动调 `_http_fetch()` 兜底
- 两种策略都在 HTTP 完全失败时保留原有行为（抛异常或用浏览器 HTML）

### 依赖
- `curl-cffi 0.15.0`（已安装）— 仅 IOP 回退路径使用，不影响其他 publisher

### 文件改动
- `src/sources/publisher.py`:
  - `BasePublisherScraper` 新增 `http_fallback_mode` / `http_fallback_strategy` 类属性
  - `BasePublisherScraper` 新增 `_http_fetch()` / `_is_bot_page()` 方法
  - `fetch_page()` 增加两阶段 fallback 逻辑
  - `NatureScraper` 配置 `requests` + `primary`
  - `IOPScraper` 配置 `curl_cffi` + `fallback`
- `tools/compare_browsers.py`: 新文件，Playwright vs Cloakbrowser 对比诊断脚本

# 已知问题

| # | 问题 | 影响 | 状态 |
|---|------|------|------|
| K1 | Pipeline 页面 Phase E2 (MinerU) 的日志无法在实时日志窗口中显示。根因推测为子进程 `FileHandler` 块缓冲导致 SSE 文件大小增量检测不到新内容。 | 低（日志仍在文件中，仅 SSE 流不可见） | 待复现后修复 |
| K2 | `tools/convert_md_to_pdf.py` 使用 pandoc `--mathml` 路径，`\(`/`\[\]` 公式渲染空白。替代方案：`src/processors/md_to_pdf_katex.py`（KaTeX + cloakbrowser，支持公式，**实验性**，标题间距待优化） | 中 | 已提供替代工具 |

# 06-14: Keywords YAML 重构 — scope_definition 重组

## 背景

原来 6 个子域的设计（尾场加速/离子加速/等离子体诊断/束流传输/辐照应用/AI控制）存在两个问题：
1. 包含了组里**不研究**的 LWFA（尾场加速），post-acceleration 被 GPT 误归类到 LWFA
2. 组员关心的关键词（EMP/探测器/烧蚀等离子体诊断/post-acceleration/FLASH）散落在错误的子域或缺失

## 决策

### 从 6 子域 → 4 大方向

重新对齐为四大方向（与组内研究的对应关系一致）：
1. **acceleration**（加速）：激光驱动离子加速 + post-acceleration
2. **plasma_physics**（等离子体）：激光等离子体物理 + 所有诊断 + FLASH
3. **beam_applications**（束流应用）：探测器系统 + EMP + 辐照应用
4. **advanced_technology**（先进技术）：束流传输/等离子体光学 + AI

LWFA 被注释保留，需要时取消注释即可激活。

### 新增 `context_gates` 全局消歧层

高歧义词（plasma、AI）在进入子域匹配前先做语境消歧，减少 fusion/space/semiconductor 等语境下的误判。每个 gate 包含 term + description + relevant_contexts + irrelevant_contexts。

### 设计原则变更

从 "子域作为分类标签" 变成 "子域作为研究方向集合"——加新关键词只需往 topics 后附加一行，无需理解 rules/triggers 等复杂结构。`priority_hint` 作为纯软约束保留。

## 改动文件

- `configs/keywords.yaml`：完全重写结构
- `src/config.py`：`load_keywords()` 返回新增 `context_gates`；`build_scope_block()` 新增 `context_gates` 参数，渲染 3 层（全局消歧 → 子域 → 不相关领域）
- `src/processors/paper_relevance.py`：`PaperRelevanceChecker` 存储 `self.context_gates`，传给 `build_scope_block()`
- `src/pipeline/phase_h.py`：调用 `build_scope_block()` 时传入 `context_gates`

## 验证

测试通过。生成的 scope_block 文本格式：

```
# Research Scope Definition

# Global Context Rules
## Term: "plasma"
...
Relevant contexts:
  - ...
Irrelevant contexts:
  - ...

# Sub-Domain: acceleration
Typical relevance level: A
...
涉及方向包括：
- ...

# Irrelevant Fields
...
```

**遗留计划**：

| # | 问题 | 计划 |
|---|------|------|
| P2 | `get_all_papers()` 全表加载 | 改为 COUNT 聚合查询 |
| P3 | `SemanticFilter` 类级缓存 | 避免多次加载 sentence-transformers 模型 |
