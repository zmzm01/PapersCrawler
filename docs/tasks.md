> 此文档记录执行步骤、关键决策和经验教训。是精炼的上下文。

## 2026-07-27 P8: 删除 GitHub 链接

- **删除 GitHub 链接**：用户反馈侧栏下方的 `github` 文字链接「不好看」，决定整个删除。涉及 `base.html` 删 `<a class="sidebar-github-link">`、style.css 删 `.sidebar-github-link` / `.sidebar-github-link:hover` 规则、docs/design.md 与 usage.md Dashboard 行去掉相关描述。
- **未触动**：侧栏 3 项导航、Dashboard 内容、Weekly chart 3 桶、i18n（无 github 残留键）。
- **结论**：P5→P6→P7→P8 经历 4 轮 GitHub 链接迭代（图标 / 颜色 / 位置 / 文字 / 删除），最终确认 WebUI 不暴露外部链接入口。

## 2026-07-27 P7: Weekly Chart 回退 3 桶 + GitHub 图标→文字

- **Weekly chart 回退 3 桶**：P6 的 4 桶重构（reported/pending_report/failed/skipped）被证明方向错误，用户需求是 matched explained.html.j2 的 3 桶设计（reportable/total_failed/other）。后端 SQL 回退到 `SUM(CASE ...)` 简单聚合，前端 3 段 bar（success/failed/pending ）+ 3 项 legend。`--pending` CSS 变量恢复 `#94a3b8`，`--pending-report` 删除。
- **GitHub 图标→文字**：移除 sidebar-footer div，在 sidebar-header 和 sidebar-nav 之间插入 `<a class="sidebar-github-link">github</a>`。CSS 小字淡灰 `rgba(255,255,255,0.6)` + monospace。删除 `nav.github` i18n 键、`.sidebar-footer`/`.github-link`/`.chart-bar.pending-report`/`.c-pending-report` 等死样式。
- **CSS 清理**：`.sidebar` 移除 flex-direction column（无需 footer 贴底），`.sidebar-nav` 移除 flex:1。
- **文档同步**：design.md/usage.md Dashboard 行更新为 3 桶 + github 文字描述。tasks.md 追加本条。

## 2026-07-27 P6: GitHub 图标移位 + Weekly Collection 4 桶重构

- **GitHub 图标移到底部**：从 `sidebar-header-actions` 移到新建 `sidebar-footer`（`sidebar-nav` 之后），白色 `#fff` + 1.5rem + 居中。删除 `sidebar-header-actions` 容器。侧栏 flex column 布局，`sidebar-nav flex: 1` 让 footer 贴底。
- **Weekly Collection 4 桶重写**：后端 SQL 从 3 桶（reportable/total_failed/other）重构为 4 个互斥桶——`reported`（已报告，绿色）/ `pending_report`（待报告，琥珀色）/ `failed`（处理失败，红色）/ `skipped`（LLM 过滤，灰色）。SQL 以顶部分支优先构成互斥链，验证 0 重叠。前端渲染同步 4 段柱状图 + legend 4 项。
- **CSS 新增**：`--pending-report`（`#f59e0b`）/ `--skipped` 改为灰 `#94a3b8`（原琥珀色让给 pending-report）/ `.chart-bar.pending-report` / `.c-pending-report` / `.sidebar-footer` / 更新 `.github-link` 白字大号。
- **i18n 替换**：删 `dashboard.weekly_reportable` + `weekly_other`，增 `weekly_reported` / `weekly_pending_report` / `weekly_skipped`（zh + en）。
- **SQL 验证**：bucket sum(7178) ≤ total(7188)，10 篇 in-process；0 篇落入 2+ buckets。
- **文档同步**：design.md 更新 Dashboard 行（4 桶说明）/ tasks.md 追加。

## 2026-07-26 P5: WebUI 进一步瘦身

- **删除 3 个页面**：Home（`home.html` 118 行）、Pipeline（`pipeline.html` 87 行）、Logs（`logs.html` 44 行）
- **路由精简**：`/` 改为 302 重定向到 `/dashboard`；删除 `/pipeline`、`/pipeline/logs` SSE、`/logs` 路由。保留 `/pipeline/status` 和 `/pipeline/weekly-stats`（Dashboard 依赖）
- **死代码清理**：删除 `PHASE_LABELS`、`PHASE_ORDER`、`_PHASE_KEY_MAP`、`_get_effective_skip`、`_atomic_write`、`RESET_DEFS`、`RESET_CASCADE`、`_run_phase_subprocess`、`_log_event_stream`、`_running_phase`、`_phase_lock` 等 ~200 行。清理 `StreamingResponse`、`CFG`、`PROMPTS_DIR` 等死 import。App.py 从 546 行减至 ~160 行
- **Dashboard 精简**：删除 `pipeline phases` 统计卡片（`phase_count`）；`_pipeline_status()` 返回值移除非必需的 `effective_skip`；`dashboard_page` 模板上下文删除 `phase_count`
- **pending→skipped UI 合并**：Dashboard 柱状图渲染时 `skippedTotal = counts.skipped + counts.pending`，legend 从 4 项改为 3 项（去掉 pending）。后端数据不动
- **Sidebar 精简**：base.html 导航从 6 项减至 3 项（Dashboard / Papers / Report），新增 GitHub 图标链接（`sidebar-header-actions` flex 容器）
- **i18n 清理**：app.js 删除 `nav.home`、`nav.pipeline`、`nav.logs`、`logs.*`(3)、`home.*`(~24)、`pipeline.*`(8 个除 success/failed/skipped)、`dashboard.phases`；新增 `nav.github`
- **CSS 清理**：删除 `.hero*`、`.home-section*`、`.tech-stack*`、`.qs-*`、`.phase-table*`、`.badge-pending`、`.log-viewer*`、`.log-controls*`、`.pipeline-toolbar`、`.phase-actions`、`.chart-bar.pending`、`.c-pending`、`--pending` 变量。新增 `.sidebar-header-actions`、`.github-link` 样式。文件从 749 行减至 ~540 行
- **文档同步**：design.md 页面功能表删除 Home/Pipeline/Logs 行、更新 Dashboard 行（pending→skipped 合并说明）；usage.md 删除 Home/Pipeline/Logs/DataSources/Subscriptions/Config 行、新增 GitHub 图标位置说明

## 2026-07-26 P4: WebUI 安全加固 R1-R4

- R1 路径遍历：`/report/data/{filename}` 和 `/report/download/{filename}` 加 `Path.resolve()` + `startswith` 防护，返回 400 而非 200+泄露
- R2 DOMPurify：base.html 追加 `dompurify@3.2.4` CDN（cdnjs）；report.html `renderReportContent()` 中 `marked.parse()` 输出经 `DOMPurify.sanitize()` 净化（保留 `target` 属性）
- R3 innerHTML→textContent：logs.html filter 函数改用 `textContent` 安全赋值（CSS 已有 `white-space: pre-wrap`）
- R4 安全响应头：`@app.middleware("http")` 注入 `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` / `Permissions-Policy`
- 文档同步：design.md 定位节重写（只读定位）、页面功能表精简（删 Data Sources/Subscriptions/Config 行 + 删任务执行模型/Reset 级联逻辑整段）、新增 WebUI 安全章节；tasks.md 追加本条
- 验证：pytest 233 passed，路径遍历返回 400，安全响应头全部存在
- 文件清单：src/web/app.py (+24/-4)、src/web/templates/base.html (+1)、src/web/templates/report.html (+3/-1)、src/web/templates/logs.html (+2/-2)、docs/design.md (重写定位+页面表+启动方式，新增安全章)、docs/tasks.md (+15 行)

## 2026-07-26 P3: 新建 CLI 工具 + 单元测试

- 新建 `tools/run_pipeline.py` — 统一流水线 CLI 入口，替代 `schedule_daily.py` / `schedule_weekly.py` / `src/main.py`
  - 互斥模式：`--daily` / `--weekly` / `--all` / `--phases A,B,C`（默认 `--all`）
  - 参数：`--dry-run`、`--reset-publisher`/`--no-reset-publisher`、`--reset-mineru`/`--no-reset-mineru`、`--log-level`
  - 复制 `schedule_daily.py` 的 logging + auto-reset 逻辑
  - `--dry-run` 打印执行计划但不调用任何 pipeline 函数
  - 顶部 docstring 含所有调用模式 + cron 配置 + xvfb-run 提示
- 新建 `tools/send_report.py` — CLI 邮件发送工具，复用 `phase_h_email()`
  - 必填 `--report` + 可选 `--recipients` / `--dry-run` / `--log-level`
  - AUTO_REPORT_DIR / USER_REPORT_DIR 双目录查找，文件不存在 exit code 2
  - `--recipients` 解析：逗号分隔、去空白、保留非空项
- 新建 `tests/test_run_pipeline.py` — 8 个测试覆盖两个 CLI 工具
  - subprocess 验证退出码和输出 + unittest.mock.patch 验证函数调用
  - 测试 dry-run 不调用 run_pipeline、phases 解析、empty phases 处理、daily 调用 run_daily
  - 测试 send_report missing exit code 2、recipients 透传、默认收件人回退
- 文档同步：`docs/usage.md` 新增 `run_pipeline.py` / `send_report.py` 条目，标记旧入口 deprecated

**关键设计决策**：
- CLI 脚本用 `main(argv=None)` 函数包装，`if __name__ == "__main__"` 只调用 `main()`，便于测试直接导入并传参
- `send_report.py` 的 `DatabaseClient` 在 `main()` 内部按需导入（非模块级），避免导入副作用
- 测试使用 subprocess（验证退出码）+ mock（验证函数调用）混合策略

**验证结果**：8 passed in 2.07s

**文件清单**：
| 文件 | 行数 | 说明 |
|------|------|------|
| `tools/run_pipeline.py` | 209 | 统一流水线 CLI 入口 |
| `tools/send_report.py` | 169 | CLI 邮件发送工具 |
| `tests/test_run_pipeline.py` | 209 | 8 个测试用例 |

## 2026-07-26 P2: 合并配置层到 settings/email.yaml

- 删除 data/skip_overrides.json（WebUI 引入的运行时层，现已无 UI 引用）
- 删除 SQLite subscribers 表 + 4 个函数
- 新建 data/email.yaml，格式 [{email, name, enabled}]，per-user 开关
- phase_h.py 收件人来源从 DB 改 email.yaml，回退 .env SMTP_TO_ADDRS
- runner.py 删 _load_skip_overrides / _get_effective_skip，use_overrides 参数废弃
- app.py 同步清理
- 文档同步（design.md / tasks.md / usage.md）

# 变更汇总

| 模块 | 变更 | 日期 |
|------|------|------|
| **CLI 工具 + 测试** | 新建 `tools/run_pipeline.py`（统一入口，替代旧 main/schedule_*）、`tools/send_report.py`（邮件发送）、`tests/test_run_pipeline.py`（8 测试）；文档同步 | 07-26 |
| **报告预览工具** | 新增 `tools/preview_report.py`：生成报告但**不**调 `mark_papers_reported()`，完全不污染数据库；已报告论文（`report_date NOT NULL`）也可再次包含，便于重看历史或生成回顾性快照。**与 Phase G auto 模式的关键差异**：(1) 不调 `mark_papers_reported()` → 下次 Phase G 仍能拾取这些论文；(2) SQL 去掉 `report_date IS NULL` 过滤 → 允许回看已报告论文；(3) `--scope` 参数决定论文范围（`all` 全部 / `week` 近 7 天 / `today` 当天），按 `created_date` 过滤；(4) 输出路径由 `--output` 必填指定（必须 `.md` 结尾），不写默认 `data/reports/auto/`；(5) explainer 文件名强制 `report_<ref_date>_explained.html`（`ref_date` 默认今天，`--date YYYY-MM-DD` 覆盖），让 explainer 的 `_extract_date_from_path` 正确识别日期，避免 "using today" warning；(6) 可选 `--no-explainer` 跳过 explainer 生成。**实现**：(1) 不依赖 `phase_g_report()` user 模式（user 模式需 doi_list），直接调底层 API：自定义 SQL + `generate_report` + `write_explained_html`；(2) `_build_paper_dicts()` 镜像 `phase_g.py:90-114` 20 字段构造逻辑；(3) `_atomic_write()` 用 `tmp + rename` 防半写文件。**CLI**：`--scope {all,week,today}` (默认 all) / `--output PATH` (必填 .md) / `--date YYYY-MM-DD` (默认今天) / `--no-explainer`。**验证**：跑 4 种 scope 组合 + 2 种错误路径（错误日期格式 / 错误输出后缀），运行前后 `report_date NOT NULL` 计数不变；自定义 `--date 2026-07-20` 时 explainer 无 "using today" warning；`--scope today` 今天无新论文时正常返回 0 篇。 | 07-26 |
| **报告解释页模板** | 创建 `templates/report/html/explained.html.j2`：独立风格、零外部依赖，复用现有 Jinja2 env（`loader` 指向 `templates/report/`）。模板输出单文件自包含 HTML，含 4 统计卡片 + 5 阶段 CSS 堆叠柱状图 + 近 7 天采集图 + 完整 `relevance_prompt` / `summary_prompt` `<details>` 快照。字体栈为系统字体，无 CDN/Google Fonts/KaTeX。渲染 mock 验证通过（14.6KB）。后续由 `pipeline.generate_explained_html` 调用并生成 `report_YYYYMMDD_explained.html`。 | 07-26 |
| **报告解释页** | 新增 `report_YYYYMMDD_explained.html`：在 Phase G 写完 md 报告后，由 `pipeline.generate_explained_html` 控制生成。HTML 含 4 统计卡片 + 5 阶段状态柱状图 + 7 天每日采集 + 完整 relevance/summary prompt 快照（`{scope_block}` 展开 + `{title}/{abstract}` 保留）。模板 `templates/report/html/explained.html.j2` 独立风格，零外部依赖，复用现有 Jinja2 env。开关默认 `true`，关闭后行为不变。 | 07-26 |
| **Phase E Prompt 三步决策树重构** | 把 `context_gates` / `irrelevant_fields` / `scope_definition` 三个字段的职责明确分层，对应 Phase E LLM 决策树三步，消除 `irrelevant_fields` 与 `context_gates` 的内容重叠。改动：(1) `src/config.py:build_scope_block()` 渲染顺序调整 `context_gates → irrelevant_fields → scope_definition`，每节标题加 `# Step N: ...` 前缀与决策树 (a)(b)(c) 步骤对应；(2) `configs/prompts/relevance.yaml` task 指令从原 5 条编号规则改为 (a)(b)(c)(d) 决策树：(a) 应用 Context Gates 做 per-term 消歧（out-of-scope 标记的 term 不得进入 sub-domain 匹配）→ (b) 论文主话题是否匹配 Irrelevant Fields（YES → D + MatchedSubfields 空 + 停止）→ (c) 分配 A/B/C/D（A=直接研究子域/B=方法技术可迁移/C=同领域但距离远/D=不在研究领域）→ (d) A/B 列出最多 2 个 sub-domain key；A/B/C/D 完整定义在 (c) 步内重述防 LLM 遗忘 D 兜底；(3) `configs/keywords.yaml` `irrelevant_fields.topics` 删除被 context_gates 覆盖的 4 项（Fusion / Space plasma / Semiconductor plasma / General AI/ML），保留仅 Collider physics + General laser physics 两项（属于"term 消歧抓不住、必须靠 topic 整篇匹配"的主题），头部注释改为三步关系说明 + 维护原则（"context_gates 已覆盖的不再写进 irrelevant_fields"）；(4) `tests/test_relevance.py` 新增 4 个测试：3 步渲染顺序断言（位置 gates < irrelevant < sub-domain）、决策树 (a)(b)(c)(d) 文本存在、A/B/C/D 4 个 anchored 描述存在、`irrelevant_fields.topics` 回归保护（防重新添加 Fusion/Space plasma/Semiconductor plasma/General AI/ML）；(5) `docs/design.md` 字段分工表 + Phase E Prompt 构建流程图 + Prompt 策略节全部更新为三步关系。**关键设计**：context_gates 与 irrelevant_fields 不合并但**同时维护**，前者 per-term 词义消歧、后者 topic-level 黑名单，是决策树中两个不同过滤层不可替代。`pytest` 验证渲染顺序 + 决策树结构 + 回归保护全部通过。 | 07-25 |
| **Papers 页 sort=relevance 改为 sort=summary（按 LLM 总结生成时间排序）** | Papers 排序选项 **Relevance Date**（`sort=relevance`，按 `llm_relevance_date DESC`）改为 **Summary Date**（`sort=summary`，按 `llm_summary_date DESC`）——语义更准确：用户想看「最近生成总结的论文」而不是「最近被 LLM 判定相关性的论文」，后者对论文生命周期理解价值更低。改动：(1) `src/db/database.py:991-1043` `get_papers()` 排序项 `relevance` → `summary`，对应 `ORDER BY llm_summary_date DESC, created_date DESC`；SELECT 列表追加 `llm_summary_date`（之前未 SELECT）。(2) `src/web/app.py:507` `/papers` 路由白名单 `("created", "published", "relevance")` → `("created", "published", "summary")`。(3) `src/web/templates/papers.html` Sort by 下拉 `value="relevance"` → `value="summary"`，i18n key `papers.sort_relevance` → `papers.sort_summary`，文案「Relevance Date」→「Summary Date」/「LLM 判定时间」→「总结生成时间」；Date 列显示逻辑 `sort_by == 'summary'` 时切换为 `p.llm_summary_date`（保持排序键与展示列一致，避免「按 X 排序但看到 Y」的混乱）。(4) `src/web/static/js/app.js` 双语 i18n key 重命名 + 文本更新。(5) `docs/design.md` Papers 行 URL 扩 `&sort=created|published|summary`；**`docs/tasks.md`** 追加本条。**`179 pytest passed`**。**注意点**：`sort=relevance` 旧 URL 现在会 fallback 到 `created`（白名单不通过），如需保留老链接兼容可在 `order_clause` 增加 `summary: [...]` 别名指向同一 ORDER BY，本次未做。 | 07-25 |
| **WebUI Pending Report A/B 过滤 + Papers 分页** | (1) **Dashboard Pending Report 过滤加上 A/B 显性约束**：`src/web/app.py:162` SQL 从 ``WHERE llm_summary_status='success' AND report_date IS NULL`` 扩展为 ``WHERE llm_summary_status='success' AND report_date IS NULL AND llm_relevance_status='success' AND llm_relevance_category IN ('A','B')``；更符合语义——C/D 类论文不应进入用户报告，i18n `dashboard.pending_report` 文案加 `(A/B)` 后缀（中文「待报告 (A/B)」、英文「Pending Report (A/B)」）。(2) **Papers 页面加分页**：`src/db/database.py` `get_papers()` 新增 `offset=0` 参数 + 同步 `LIMIT ? OFFSET ?`；新增 `get_papers_count(category_filter=None)` 辅助（不受 sort_by 影响，count 与 list 共用相同 WHERE 条件）。`src/web/app.py:497-525` `/papers` 路由新增 `page: int=1` + `per_page: int=100` query 参数；`per_page` 白名单 `50/100/200`（其他值 fallback 100），`page<1` fallback 1；`offset = (page-1) * per_page`；新增 `total_count` 模板变量。`src/web/templates/papers.html` 表格下方新增 `.papers-pagination` 分页器：「共 M 篇 · 第 N/T 页 · [每页 K ▾] [‹ 上一页] [下一页 ›]」，`page=1` 时上一页按钮 disabled、`page>=total_pages` 时下一页按钮 disabled，filter 切换/sort 切换/per_page 切换时 JS `changeSort/changeCategory/changeHasSummary/changePerPage` 全部 reset `page=''`（删 URL 中的 page 参数）。`src/web/static/css/style.css` 新增 `.papers-pagination` / `.page-info` / `.page-size-label` 样式（flex + gap + border-top + 移动端 wrap）。**i18n 新增 4 键 × 2 langs**：`papers.page_info`（带 `{total}/{page}/{pages}` 三个占位符） / `papers.per_page` / `papers.prev` / `papers.next`。(3) **`docs/design.md`** Papers 行 URL 追加 `&page=&per_page=` + 分段描述新增「**分页**」；新增 Dashboard 行（原本缺失）记录 `_pipeline_status()` 的 `pending_report` 计算 SQL（含 A/B 显性约束）。(4) **`docs/tasks.md`** 追加本条。**后端零行为变更**：`/report/*` / `/pipeline/*` 端点未动；`get_papers()` 老调用（CLI / 工具脚本）若未传 offset 默认 0，行为不变。**`178 pytest passed`**。**注意**：`get_papers_count()` 与 `get_papers()` 的 WHERE 条件在源码中重复定义（防止 JOIN 破坏计数准确性），未来加新 category 需同步两处；考虑后续提取为 helper 函数。 | 07-25 |
| **WebUI Report 侧栏回退到下拉选择** | 用户反馈上方「Papers / Report 拆分重构」引入的 Report 页面左侧 240px sticky 侧栏**没有正常显示**（CSS flex/sticky 在用户浏览器下未正确生效），按用户给的二选一回退到下拉选择方案。**改动**：(1) `src/web/templates/report.html` 移除 `<div class="report-layout">` 容器 + `<aside class="report-sidebar">` 整段（auto/user 分组列表 + 每条日期切片/badge/论文数/timeago），恢复单列结构；主区 toolbar 中 `<label class="mobile-report-select" style="display:none;">` 改为 `<label class="report-select-label">` **常驻可见**（不再依赖媒体查询切换）；`<select>` option 文本丰富化：``{{ r.filename[7:15] }} · {{ r.source }} · {{ r.paper_count }} papers · {{ r.timeago }}``（auto + user 按 mtime DESC 混排，无需分组）；保留 `{% if not reports %}` 空态提示。(2) `src/web/static/css/style.css` 删除 `.report-layout` / `.report-sidebar*` / `.report-list` / `.report-item*` / `.report-main` / `.mobile-report-select` 及相关 @media 整块（行 513-566，共 -54 行），回退到原 `.report-viewer` + `.report-viewer-toolbar` 单一列布局。**(3) `src/web/static/js/app.js` i18n 清理**：删除 3 个 `report.*` 死键 `sidebar_auto` / `sidebar_user` / `sidebar_empty` × 2 langs = 6 行；`report.select_hint` 文本修正：中文「请至少选择一篇论文」→「请选择一份报告」、英文「Select at least one paper」→「Select a report」（原意是 papers 选取，已不适用）。**保留** 5 个活键：`title` / `choose_report` / `no_report` / `download` / `select_hint`。(4) `docs/design.md` Report 行回退到下拉文案。(5) `docs/tasks.md` 追加本条。**后端零行为变更**：`/report/generate` / `/report/data/{filename}` / `/report/download/{filename}` / `/report/list` 端点完全保留，`_list_reports()` 仍返回 `paper_count` + `timeago`（option 文本继续使用），`?show=<filename>` URL 解析保留。**Papers 页面 / 主页 / CSS sticky-bar / toast / checkbox 列不受影响**。**`178 pytest passed`**。 | 07-25 |
| **WebUI Papers / Report 拆分重构** | 拆分 `src/web/templates/papers.html` 与 `src/web/templates/report.html` 的重叠职责——`/papers` 现承担「浏览 + 选取 + 生成」三职合一，`/report` 专做「报告档案馆」只读。**Papers 页面新增**：(1) 表格首列常驻 checkbox（无 `llm_summary_status='success'` 的论文自动 disabled + `data-i18n-title` 双语 tooltip "该论文无 LLM 总结"）；(2) 工具栏「仅可报告」过滤 checkbox + 「全选当前页」master checkbox（无任何可选项时自动 disabled）；(3) **底部 sticky 操作栏** `#sticky-selection-bar`：选中数 = 0 时 `display:none`、>0 时 `display:flex` 浮出，显示「N 篇已选 | [生成报告] [清空]」；(4) 生成逻辑：POST `/report/generate` → 成功 toast 浮窗「已生成 [filename] [查看] [下载]」+ `[查看]` 链 `/report?show=X`（保留选区上下文，不自动跳转打断选区工作流）；(5) 后端 `/papers` 路由新增 `has_summary: bool` query，无 summary 的论文由 Python 端 filter 出来（避免 DB 层改动）。**Report 页面改造**：(1) 移除论文 checkbox 表 / Select All / Deselect All / Publisher 过滤 / Generate 按钮 / Preview 区 / `auto-load first report on DOMContentLoaded` 行为；(2) 新增 **左侧 240px sticky 侧栏**：按 `auto` / `user` 来源分组，每条展示日期切片（`r.filename[7:15]`）+ 来源 badge + 论文数 + 相对时间（timeago helper）；移动端 <768px 退化为顶部下拉；(3) URL `?show=<filename>` → 解析后传 `selected_filename` 模板变量 → 页面 `DOMContentLoaded` 时 `loadReport(filename)`；(4) `_list_reports()` 新增计算字段：`paper_count` = 统计 `**DOI**` 出现次数（与 report 模板中的 meta 行对应），`timeago` = `_timeago(mtime)` 人类可读相对时间。**i18n**（`src/web/static/js/app.js`）：新增 12 papers.* key（`select_all` / `has_summary_only` / `no_summary` / `selected_count` / `clear` / `generate` / `generating` / `toast_generated` / `toast_failed` / `toast_view` / `toast_download` / `toast_network_error`）+ 3 report.* key（`sidebar_auto` / `sidebar_user` / `sidebar_empty`）；清理 12 个旧 report.* 死键（`choose_hint` / `generate_title` / `publisher` / `select_all` / `deselect_all` / `generate` / `doi` / `title_col` / `publisher_col` / `summary_date` / `preview` / `generated`），所有 report.* 键 8 × 2 langs。**触及 6 个文件**（`src/web/app.py` +58/-18，`templates/papers.html` +143/-1，`templates/report.html` +69/-130，`templates/home.html` +6/-6，`static/css/style.css` +152/0，`static/js/app.js` +78/-32）。**后端零行为变更**：`/report/generate` 仍接受 `{dois: [...]}` 返回 `{ok, filename, preview}`，`/report/data/{filename}` / `/report/download/{filename}` / `/report/list` 全部保留。**`switchLanguage()` 扩展支持 `data-i18n-title`**：title 属性也走双语切换，disabled checkbox 的 tooltip 正确国际化。**`home.html` 同步**：`/papers` 卡片改为「浏览和选取论文，生成自定义报告」+ 新增 `home.papers_notes`；`/report` 卡片改为「查看已生成的报告，按来源/日期筛选」+ 新增 `home.report_notes`；guide table 同步。**`docs/design.md`** Papers / Report 行重写。**`178 pytest passed`**。**遗留**：paper_count 用 `**DOI**` 字符串计数估算，若 `templates/report/` markdown 模板里元信息格式调整需同步更新 `_list_reports()` 的统计规则。**后续**：「侧栏未正常显示」已通过上方「Report 侧栏回退到下拉选择」条目回退。 | 07-25 |
| **Papers 页 A/B 筛选** | Papers 页面默认仅展示 LLM 判定为 A/B 相关的论文（`llm_relevance_status='success' AND llm_relevance_category IN ('A','B')`），与 `get_relevant_papers()` 查询条件保持一致。改动：(1) `src/db/database.py:984` `get_papers()` 新增 `category_filter` 参数（`'ab'` 走 WHERE 过滤，`None`/`'all'` 不过滤）；(2) `src/web/app.py:495` `/papers` 路由新增 `category` 查询参数（默认 `ab`，白名单 `ab`/`all`），传递给 `db.get_papers()` 并透传到模板；(3) `src/web/templates/papers.html` 工具栏新增「LLM Category」下拉（A/B Only / All）+ 空结果 alert；(4) `src/web/static/js/app.js` 新增 4 个 i18n key（`papers.category_label` / `category_ab` / `category_all` / `empty`）中英文；(5) `docs/design.md` Papers 行追加参数说明。JS 工具函数 `_urlWithParams()` 重构原 `changeSort()` 直拼 URL 的写法，避免两个下拉相互覆盖 query 参数。默认行为变更：原行为「展示全部论文」需通过 `?category=all` 显式启用，保留全量查看能力。 | 07-25 |
| **Papers 页筛选细化** | 在 A/B 筛选基础上扩展：(a) LLM Category 下拉由 2 选项扩为 4 选项：**A Only / B Only / A/B / All**，对应 `category=a` / `b` / `ab` / `all`；(b) Sort by 下拉新增 **Relevance Date**（`sort=relevance`），按 `llm_relevance_date DESC` 排序看最近判定的论文。改动：(1) `src/db/database.py:984` `get_papers()` `category_filter` 字典化（`a` / `b` / `ab` 三个分支），`sort_by` 新增 `relevance` 排序项（额外 SELECT `llm_relevance_date`）；(2) `src/web/app.py:495` 白名单扩为 `category ∈ {a,b,ab,all}` / `sort ∈ {created,published,relevance}`；(3) `src/web/templates/papers.html` 工具栏加 `A Only` / `B Only` / `Relevance Date` 三个 option；(4) `src/web/static/js/app.js` 新增 3 个 i18n key（`category_a` / `category_b` / `sort_relevance`）中英文（原 `category_ab` 文案由 "A/B Only" 简化为 "A/B"，因下拉已有 A/B/A 单独选项，命名去重）；(5) `docs/design.md` Papers 行更新参数列表。 | 07-25 |
| **报告新增 LLM 相关性元信息** | Markdown/HTML 报告每篇论文新增两行元信息：**相关性等级**（A/B/C/D，取自 `llm_relevance_category`）+ **判断理由**（LLM 给出的相关/不相关原因，取自 `llm_relevance_reason`）。改动：(1) `src/pipeline/phase_g.py` paper_dict 增加 2 个字段透传；(2) `src/processors/paper_report_generator.py` Markdown 段和 HTML 段统一在 `出版社` 行后、`DOI` 行前插入；`判断理由` 走 `_process_results_markdown()`（Markdown）/ `_process_text_for_html()`（HTML）做 LaTeX 修复 + 字面量换行 + HTML 转义（XSS 防护）；(3) `tests/test_report.py` 新增 3 个测试：Markdown 渲染 + LaTeX 保留、空字段不渲染对应行、HTML 渲染 + XSS 防护（`& <b>`/`script` 全部转义）；(4) `docs/design.md` 报告元信息增强节补充。空值时整行省略，向后兼容。`25 pytest passed`。 | 07-25 |
| **报告头部插入相关性等级图例** | 为让读者在看到每篇论文的「相关性等级」字段时能立即理解 A/B/C/D 的判定标准，Markdown/HTML 报告**最顶端**（位于 `# 文献报告` 一级标题之前）插入相关性等级图例。定义来源：`configs/prompts/relevance.yaml` 中 Phase E LLM Prompt 的权威英文定义（A/B/C/D），转写为中文简表并标注源文件路径。改动：(1) `src/processors/paper_report_generator.py` 新增 `_RELEVANCE_LEGEND_LINES` 常量（4 条元组） + `_relevance_legend_md()`（Markdown `>` 引用块） + `_relevance_legend_html()`（HTML `<blockquote class="relevance-legend">`） 三个 helper；(2) `generate_markdown()` / `generate_html()` 顶端调用对应 helper（图例在 body 第一个字符，置于 `# 文献报告` 与 `## 论文标题` 之前），保证单篇/多篇报告都生效；(3) HTML 模板内嵌 CSS：`blockquote.relevance-legend` 浅蓝边框 + 浅灰背景（与论文 section 卡片视觉区分）+ `<code>` 源文件路径高亮；(4) `tests/test_report.py` 新增 6 个测试：helper 单元 + 报告整体位置断言（legend 在 title/section 之前）+ 旧测试 `test_report_missing_relevance_fields_omits_lines` 改用 `**相关性等级**:` 冒号格式避免与图例术语冲突；(5) `docs/design.md` 报告元信息增强节追加图例说明。`169 pytest passed`。 | 07-25 |
| **修复重跑 relevance 导致已总结论文误入报** | `get_papers_for_report()` 仅查 `llm_summary_status='success' AND report_date IS NULL`，而 `update_llm_relevance()` **不重置** `llm_summary_*` 字段，导致论文从 A/B 重判为 C/D 后仍被 `report_date=NULL` 的过滤误选入报（覆盖真实相关性判定）。修复：`(1)` `src/db/database.py:921 get_papers_for_report()` 在 SQL 增加 `AND llm_relevance_category IN ('A','B') AND llm_relevance_status='success'`，并扩 docstring 解释为何需要显式过滤；`(2)` `src/pipeline/phase_g.py:44` 用户模式 SQL（DOI 列表查询）同步加入同样的 relevance 过滤，保持 auto/user 两种模式语义一致；`(3)` `tests/test_db.py` 旧 `test_get_papers_for_report` 补 `update_llm_relevance` 设 A 类（否则新过滤下 s1/s2 都无 relevance 入报失败），新增 `test_get_papers_for_report_excludes_reclassified_papers` 回归测试：先 A 总结成功 → 断言入报，再重判 D → 断言 `get_papers_for_report() == []`；`(4)` `docs/design.md` 报告状态节追加「显式 relevance 过滤」段。`179 pytest passed`。**未做**：级联重置（option 2）—— Phase E 检测到 A/B→C/D 时不主动清 summary，避免改动 Phase F / G 逻辑；如需更严格一致性可后续加 `invalidated` 枚举值。 | 07-25 |
| **报告元信息重排 + 删除冗余字段** | 用户反馈「相关方向」判定过宽、「期刊」与「出版社」重叠、「PDF」链接点击率低，删除并重排元信息顺序。**新顺序**：期刊 → 作者 → 日期 → DOI → 页面 → 相关性等级 → 判断理由 → 原文摘要 → 一句话（后接 4 个 H3 子节保持不变）。改动：`(1)` `templates/report/markdown/paper.md.j2` 重写元信息行宏：删 `p.publisher` / `p.matched_subdomains_labels` / `p.pdf_url` 三行，重排剩余行顺序（期刊先、相关方向整行移除）；`(2)` `templates/report/html/paper.html.j2` 同步重写（HTML `<p>` 内字段顺序与 Markdown 一致）；`(3)` `src/processors/paper_report_generator.py` 新增 `_RELEVANCE_RANK = {"A":0,"B":1,"C":2,"D":3}` + `_sort_papers(papers)` helper（稳定 sort：先 date 倒序再 category 升序，等价「A 先、同级最新在前」），`generate_markdown` / `generate_html` 内部调用（之前 `phase_g.py` 的 `paper_list.sort(key=journal+date)` 删除，由 generator 统一负责）；`(4)` `tests/test_report.py` 删 3 个 `test_report_*subdomain_labels*` 旧测试（功能已删除），新增 5 个元信息测试（`test_report_no_subdomain_in_metadata` / `test_report_no_publisher_no_pdf_in_metadata` / `test_report_metadata_new_order` 顺序断言 / `test_report_html_metadata_new_order` / `test_report_later_sections_unchanged`）+ 4 个排序测试（相关性等级优先 / 未知 category 排末 / 同级空日期排末 / 端到端 A 在 B 前）；`(5)` `docs/design.md` 报告元信息增强节重写：「**当前**」新顺序 + 「2026-07-25 调整」删除/重排说明 + 排序节改写稳定 sort 解释。`184 pytest passed`（test_report.py 40 个）。`matched_subdomains` / `pdf_url` / `publisher` 字段从 payload 中**保留**（Phase G 与 WebUI 可能仍用），仅在 paper 模板不渲染。 | 07-25 |
| **报告解释页删除 stats grid（2026-07-25 第 2 轮简化）** | 用户认为「也没人在意」stats grid（总论文/待报告/出版社 3 个 stat-card），与上一轮删除的两个 chart 一并清出。改动：`(1)` `templates/report/html/explained.html.j2`（210 → 109 行）：删 `<section class="dashboard">` 整块 + 相关 CSS（`.dashboard` / `.stats-grid` / `.stat-card` / `.stat-value` / `.stat-card.warning` / `.stat-label`）+ `--c-failed` 颜色变量（仅 stat-card.warning 用）；`(2)` `src/processors/report_explainer.py`（174 → 130 行）：`_collect_dashboard_data` 删 3 个 SQL（`total_papers` / `pending_report` / `publishers_count`）+ 3 个返回 key；`db` 参数**保留**（API 稳定性 + 未来可能用）；module docstring History 段新增「2nd pass」说明；`(3)` `tests/test_explained_html.py`（9 → 7 个测试）：删 `TestCollectDashboardData.test_counts` + `test_empty_db`（无统计可断言）；更新 `test_structure_with_data` 与 `test_all_template_variables_present` 的 expected/required keys 集合（7 → 4）；更新 `TestWriteExplainedHtml.test_happy_path` 的「不存在」断言集合：移除 `阶段`（旧 stat-card 标题），新增 `总论文` / `待报告` / `出版社` 三个新断言（确保 stats grid 真的不渲染）；`(4)` `docs/design.md` 报告解释页节：页面结构从 6 项简化为 3 项（Header / Prompt 快照 / Footer），模板变量从 10 个简化为 4 个，新增「2026-07-25 简化历史」记录两轮删除。`222 pytest passed`（test_explained_html.py 7 个 + 删 2 个旧 count 测试）。**当前解释页仅含 Prompt 快照**，与日报主报告形成「看论文 vs 看判定依据」互补定位。 | 07-25 |
| **报告头部简化 + 排序说明** | 用户二次反馈：图例的「（依据 `configs/prompts/relevance.yaml` ...）」来源注释冗余可删；首行元信息应为「期刊」而非「出版社」；报告最前需加一行「报告排序」说明。改动：`(1)` 头部 legend 模板（`templates/report/{markdown,html}/legend.{md,html}.j2`）删除来源路径注释，仅保留 A/B/C/D 简表；`(2)` paper 模板（`templates/report/{markdown,html}/paper.{md,html}.j2`）把 `p.publisher` / `出版社` 改回 `p.journal` / `期刊`（即恢复第 1 版删除的字段，因为更具体）；`(3)` 新增两个排序说明模板 `templates/report/{markdown,html}/sort_note.{md,html}.j2`（含 `sort_note()` 宏），`document.{md,html}.j2` import 并在 legend 之前渲染（Markdown `> **报告排序**` / HTML `<blockquote class="sort-note">`），告知读者排序规则；`(4)` `templates/report/html/style.css` 新增 `blockquote.sort-note` 样式（淡黄底 + 金色左竖线，与 `blockquote.relevance-legend` 浅蓝底区分）；`(5)` `tests/test_report.py` 更新断言：`test_report_no_publisher_no_pdf_in_metadata`（替代原 `test_report_no_journal_no_pdf_in_metadata`）、`test_report_metadata_new_order` 第一字段改 `期刊`、`test_relevance_legend_*` 删 `relevance.yaml` / `Phase E LLM Prompt` 断言改 `not in`、`test_template_legend_contains_all_levels` 同步更新；新增 2 个排序说明测试（`test_report_sort_note_appears_at_top_{markdown,html}`，HTML 版用完整 `<blockquote class="sort-note">` 匹配避免与 CSS 子串冲突）。`186 pytest passed`（test_report.py 42 个）。 | 07-25 |
| **报告头部新增「其他说明」块** | 用户补充：报告最前需 3 条局限性说明，解释收录量波动 / RSS 回溯 / LLM 判定内在偏差。`优化后的文本`（每条独立可读）：`(1)` 筛选 prompt 调整后，部分历史文献可能被重新召回，使单次报告收录量明显增加。`(2)` RSS 历史回溯可能纳入较早发表（数月甚至数年前）的文献。`(3)` 相关性判定受 prompt 表述、LLM 能力上限及仅以摘要为输入的信息局限影响，结果可能存在偏差，请结合论文全文进一步判断。改动：`(1)` 新增 `templates/report/{markdown,html}/disclaimers.{md,html}.j2`（含 `disclaimers()` 宏，Markdown 引用块 / HTML `<blockquote class="disclaimers">`），`document.{md,html}.j2` import 并在 legend 之后渲染，形成「排序（黄）→ 图例（蓝）→ 说明（橙）」三色头部；`(2)` `templates/report/html/style.css` 新增 `blockquote.disclaimers` 样式（淡橙底 + 橙色左竖线 `#e67e22`），与 `sort-note`（黄）和 `relevance-legend`（蓝）形成视觉区分；`(3)` `tests/test_report.py` 更新 `test_report_sort_note_appears_at_top_{markdown,html}` 断言在 `legend_idx < section_idx` 之间增加 `disclaimers_idx`（4 元素顺序），新增 `test_report_disclaimers_contain_three_points` 验证 3 条关键词 `筛选 prompt 调整` / `RSS 历史回溯` / `仅以摘要` 在 MD + HTML 中均出现。`187 pytest passed`（test_report.py 43 个）。 | 07-25 |
| **报告内容模板外置** | 把 `src/processors/paper_report_generator.py` 中硬编码的 Markdown/HTML 报告 f-string 模板迁出到 `templates/report/` 目录，便于用户自定义报告版式。设计：(1) 7 个文件 —— `markdown/{legend,paper,document}.md.j2` + `html/{legend,paper,document}.html.j2` + `html/style.css`（样式独立文件方便编辑）；(2) `src/config.py:70` 新增 `REPORT_TEMPLATE_DIR` 常量指向 `templates/report/`（与 `EMAIL_TEMPLATE_DIR` 同级约定）；(3) `src/processors/paper_report_generator.py` v3 重写：新增 `_get_template_env()` 懒加载 Jinja2 Environment（`autoescape=False` 避免双转义，因 HTML 转义已在 `_process_text_for_html` 完成；`trim_blocks + lstrip_blocks + keep_trailing_newline` 控制空白）+ `_load_style_css()` 读 CSS 文件 + `_make_paper_payload_md/html(paper, scope_definition)` 在 Python 端做所有文本处理后产出干净 dict 给模板；模板内部用 Jinja2 宏（`legend()` / `paper(p)`）和 `{% import %}` 复用（**注意**：import 路径是相对 loader root，不能省略子目录）；删除原 `_RELEVANCE_LEGEND_LINES` 常量（已迁出到 legend 模板）+ 删除 `_make_markdown_section` / `_make_html_section` 整个 f-string 实现；保留所有 `_process_*` / `_fix_latex_backslashes_for_display` / `_convert_literal_newlines` / `_adjust_headings` helpers 供 payload 函数调用；(4) `tests/test_report.py` 新增 4 个测试：模板文件存在性（含 `style.css` 嵌入校验）+ Jinja2 Environment 加载所有 6 个 .j2 + legend 模板直接 `tpl.module.legend()` 渲染含 A/B/C/D + 完整 HTML 含 `blockquote.relevance-legend`；(5) `docs/README.md` 项目结构补 `templates/report/` 路径。**关键设计**：Python 端做文本处理（LaTeX/换行/HTML 转义），模板端只做结构渲染 —— 避免在 Jinja 表达式中混 filters 导致转义逻辑难审计。`173 pytest passed`。 | 07-25 |
| **Pipeline 全面 Code Review** | @oracle 独立深度阅读 19 个假设 + 全量扫描 pipeline/sources/processors/db（共 ~7000 行），定位 **2 个 production-breaking bug + 1 个设计回归 + 14 个质量改进**。详见下方「2026-07-24 — Pipeline 全面 Code Review」节。**已确认问题（按优先级）**：CRITICAL #1 `runner.py:130` `DAILY_PHASES=["A-RSS","A-CR","B","C","D","E","E2","F"]` 含 `"D"` 但 `phase_map`（line 83-93）无 `"D"` 键 → 每次 schedule_daily.py 执行到 "D" 触发 `KeyError`，Phases E/E2/F 永不执行；CRITICAL #2 `phase_g.py:117` `db.mark_papers_reported()` 先于 `md_path.write_text()`（line 132），中间崩溃 → 论文永久 `report_date` 标记但无文件，后续 `get_papers_for_report()` 过滤 `report_date IS NULL` 永久丢稿；HIGH #3 `phase_b.py:46-60` 作者缺失仅 warning 仍标 SUCCESS（design.md/tasks.md 2026-05-23 明确"标记 failed" → 漂移回归）；HIGH #4 `DatabaseClient` 无 `close()`/`__enter__`/`__exit__`，SQLite 连接泄漏；HIGH #5 `CFG.LLM_CONCURRENT_MAX=100` 默认值过高 → DeepSeek 限流 429 风暴；HIGH #6 `phase_e2.py:107-129` 8 空格缩进混合 4 空格；HIGH #7 `tools/schedule_weekly.py:27-42` 模块级 `mkdir`+`basicConfig`（对比 schedule_daily.py 应在 `__main__` 块内）。**19 假设验证**：CONFIRMED H1/H6/H12/H13/H17/H19 + REFUTED H2/H3/H4 + NEEDS_MORE_INFO H5 + 设计意图 H7-H11/H14-H16/H18。**架构建议**：所有 client 类（Database/Crossref/RSS/MinerU/Publisher）加 context manager；`phase_g.py` 改为 temp-file + mark + rename 原子序列；`phase_a.py:242` 加 `any_success` 标志防全失败时误存 `last_run_date`；新增 `tests/test_runner_phase_map.py` 锁死 `DAILY_PHASES ⊆ phase_map.keys()`（可拦住 #1 类回归）。Web UI (`src/web/app.py`) 按用户明确要求**不在本次 review 范围**。 | 07-24 |
| **手动 PDF 导入工具** | 新增 `tools/import_local_pdf.py`：单篇模式手动导入本地 PDF，绕过 Phase E2 反复下载失败。用法 `python tools/import_local_pdf.py --doi <DOI> --pdf <PATH>`。流程：校验文件存在 + `%PDF-` 头部 → 计算 `safe_doi`（规则与 `phase_e2.py:149` 一致）→ 复制到 `MINERU_OUTPUT_DIR/<safe_doi>/paper.pdf`（复用 `src/config.py` 常量，不硬编码）→ 重置 DB 中该 DOI 的 `mineru_parse_status='pending'`、`mineru_parse_error=NULL`、`mineru_parse_date=NULL`（不动 `pdf_url`/`mineru_output_dir`/`doi`）。下次 daily 调度跑 Phase E2 时命中现有 PDF 复用逻辑（`phase_e2.py:155-162`）跳过下载直接交给 MinerU。退出码：1=文件不存在/异常，2=非 PDF 头部，3=DB 无该 DOI 记录（PDF 已落盘）。sys.path 处理与 `tools/schedule_daily.py` 一致。设计决策：方案 A（独立脚本，不改 pipeline）+ 单篇模式 + 只重置状态不自动续跑，风险最低。 | 07-20 |
| **MinerU Token 检测日志劫持修复** | 修复 `_check_mineru_token()` 在 `config.py` 模块导入时自动调用导致的日志系统劫持 bug。根因：`logging.warning()` 便捷函数在 root logger 无 handler 时会自动调用 `basicConfig()` 偷装默认 `StreamHandler`（WARNING 级别），导致入口脚本后续的 `logging.basicConfig(...)` 成为空操作（`basicConfig` 语义为"仅当 root 无 handler 时才配置"）。后果：自定义 `RotatingFileHandler` 失效（日志文件不再增长），root 级别锁在 WARNING（所有 DEBUG/INFO 被过滤）。用户观察到"WARNING 后就没有输出了"正是此现象。修复：1) `config.py:586` 删除模块级 `_check_mineru_token()` 调用，改为导出函数供入口显式调用；2) 4 个入口（`src/main.py`、`tools/schedule_daily.py`、`tools/schedule_weekly.py`、`src/web/app.py`）在 `logging.basicConfig(...)` 之后显式调用 `_check_mineru_token()`；3) `config.py` 新增注释说明此反模式的原因。验证：模拟 10 天后过期 token，新顺序下 DEBUG/INFO 正常输出，root handler 单一；旧顺序反证 root level 锁在 30(WARNING)，DEBUG/INFO 被吞。 | 07-20 |
| **20260713 报告生成缺陷修复** | 修复 4 项报告生成缺陷：1) Cambridge 摘要 URL 误用——`CambridgeScraper.parse_page` 盲信 `citation_abstract` meta，部分文章该标签为首版 PDF 图片 URL，新增 `_validate_cambridge_abstract` 校验（URL/图片扩展名→置空）；2) 字面量 `\n` 未转换——LLM JSON 输出 `\\n` 经 json.loads 解码为字面量 `\n`（反斜杠+n）而非真实换行，导致 `_adjust_headings` 行首 `^#` 正则失配，新增 `_convert_literal_newlines`（`\n` 后非字母时转真实换行，保护 `\nabla`/`\neq`/`\nu` 等 LaTeX 命令），在 `_process_text_for_markdown` 与 `_process_results_markdown` 中调用；3) 相关方向标签错配——`_build_subdomain_labels` 贪婪子串匹配把 `plasma_physics`（描述含"控制"）误判为"加速器控制与AI"，改为固定 `_SUBDOMAIN_LABEL_MAP` 按 key 查表；4) Hugo PaperMod TOC 层级——`hugo.yaml` 新增 `markup.tableOfContents: {startLevel:2, endLevel:2}` 限定目录仅收录 h2 论文标题。新增 3 个测试（字面量换行、LaTeX 保护、Cambridge URL 拒绝），更新 `test_build_subdomain_labels_known`（`advanced_technology` 标签改为"束流传输与等离子体光学"），144 pytest 全通过。 | 07-14 |
| **回退自定义 Hugo 模板，改用 PaperMod 原生布局** | 用户反馈 20260608 排版溢出未解决，判定自定义 flex 侧栏布局是根因。回退：1) 删除 `site/layouts/single.html`（自定义 flex 侧栏模板）→ 回退到主题原生 `single.html`（块级布局，TOC 为可折叠 `<details>` 渲染在正文上方）；2) 删除 `site/layouts/partials/toc.html`（自定义 h2-only + scroll-spy 目录）→ 回退到原生 `toc.html`（匹配 h1-h6 生成嵌套目录树）；3) `custom.css` 移除 `--main-width:1100px` 加宽、`.post-content-wrapper` flex 容器、`.toc-container` 侧栏样式，仅保留 `.post-content p,.post-content li { overflow-wrap:break-word; word-break:break-word; }` 不可见兜底；4) 保留 `list.html`（卡片 `.Description` 优先，与溢出无关）与 `extend_head.html`（KaTeX 渲染）。hugo 构建成功，编译 CSS 中 `post-content-wrapper`/`toc-container`/`--main-width:1100px` 全部消失，原生 `.post-content{margin:30px 0}` 块级布局生效。 | 07-13 |
| **20260608 报告排版溢出修复** | 根因：`paper_report_generator.py` 仅对 `main_results_and_physics` 字段做 heading re-leveling（`_adjust_headings`），其余 LLM 字段（motivation/method/take_home）经 `_process_text_for_markdown` 直通，LLM 在 `key_setup_and_method` 字段中输出的 `##` 子标题未被降级，渲染为 h2 破坏文档层级（TOC 侧栏将其列为独立论文条目，flex 布局下长 CJK+数学 token 溢出）。修复：1) `_make_markdown_section` 中 motivation/method/take_home 改用 `_process_results_markdown`（含 LaTeX 修复 + heading re-leveling + 换行转换），`abstract`/`one_sentence` 保留原处理；2) `custom.css` 新增 `.post-content { min-width:0; overflow-wrap:break-word; word-break:break-word; }` 兜底；3) `convert_reports_to_hugo.py` 新增 `_validate_heading_structure` 检测错位 `##` 子标题（缺 `---` 分隔符）+ h1 计数，hugo stderr 成功时也输出，`--all` 删除改为仅删 `source: auto` 的文件；4) 回溯修复 20260608 源文件与 Hugo content 中 6 处错位标题（`##`→`####`、`###`→`#####`）。20 pytest 通过，hugo 构建成功。 | 07-13 |
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

# 2026-07-24 — Pipeline 全面 Code Review

**触发**：用户要求"对代码进行全面 review，重点在于 pipeline。由于 Web UI 不计划对公网开放，存在漏洞是正常的"。

**方法**：orchestrator 收集基线上下文（项目结构、design 决策、19 个候选假设）→ 调度 @oracle 独立深度阅读全部 pipeline 源码（重点 publisher.py 1422 行、database.py 1307 行、paper_report_generator.py 670 行）→ 验证/反驳 19 假设 + 主动扫描其他风险点（资源泄漏、并发、错误处理一致性、YAGNI、状态机、SQL 注入）→ 按 CRITICAL/HIGH/MEDIUM/LOW 评级。

**评审范围（in scope）**：`src/pipeline/`、`src/sources/`、`src/processors/`、`src/db/`、`src/common.py`、`src/config.py`、`tools/`。**Out of scope**：`src/web/app.py`（用户明确）。

## CRITICAL — production-breaking

1. **`runner.py:130` `DAILY_PHASES` 含 `"D"` 但 `phase_map` 无 `"D"` 键 → `KeyError` 阻断每日 cron**
   - 现象：schedule_daily.py 跑到 "D" 时 `func, args, enabled = phase_map["D"]` 抛 `KeyError: 'D'`，Phases E/E2/F 永不执行
   - 根因：Phase D 早被删除（v3 schema migration + `tasks.md` 06-04 节"Phase D 重构"），但 `DAILY_PHASES` 列表未同步清理
   - **交叉引用**：下方「2026-07-24 — 移除 Phase D」节末尾的「⚠️ 2026-07-24 review 阶段发现：移除不完整（CRITICAL #1）」详细记录了根因 commit `dbb7435` (2026-07-24 18:56) 的疏漏，确认 bug 现存未修
   - 修复：`DAILY_PHASES = ["A-RSS", "A-CR", "B", "C", "E", "E2", "F"]` + 更新 line 137 docstring

2. **`phase_g.py:117` 标记已报先于文件写入 → 中间崩溃永久丢稿**
   - 现象：`db.mark_papers_reported()` 在 line 117，`md_path.write_text()` 在 line 132；OOM/断电/异常导致中间崩溃 → 论文永久 `report_date` 标记但无文件
   - 后果：后续 `get_papers_for_report()` 过滤 `report_date IS NULL` → 这些论文从所有未来报告消失
   - 修复：写 `.tmp` → mark → 原子 rename（与 `phase_a.py` 智能回溯的 `_save_last_run_date` 一致的原子模式）

## HIGH — 优先修复

3. **`phase_b.py:46-60` 作者缺失仍标 SUCCESS — 设计回归**
   - 漂移：design.md/tasks.md 2026-05-23 节明确"作者为空时标记 failed 而非 success"；现代码仅 `logger.warning()` 继续标 SUCCESS
   - 修复：作者空 → `FetchStatus.FAILED` + 错误信息，与设计文档对齐

4. **`DatabaseClient` 无 `close()`/`__enter__`/`__exit` → SQLite 连接泄漏**
   - 现象：长跑 WebUI 永不释放；`schedule_daily.py:48` 已开第二连接
   - 修复：加 context manager，`with DatabaseClient(DB_PATH) as db:` 模式

5. **`CFG.LLM_CONCURRENT_MAX=100` 默认过高 → DeepSeek 限流 429 风暴**
   - 现象：首次跑多 pending 论文 → 100 并发请求触发 API 限流
   - 修复：默认 5-10，`settings.yaml` 可覆盖

6. **`phase_e2.py:107-129` 8 空格缩进混合 4 空格 — 维护隐患**
   - 现象：循环体 20 空格，文件其余 16 空格；未来混合编辑即 `IndentationError`
   - 修复：re-indent + `ruff format`

7. **`tools/schedule_weekly.py:27-42` 模块级 `mkdir`+`basicConfig` — 导入副作用**
   - 现象：对比 `schedule_daily.py` 正确放在 `if __name__ == "__main__":` 块内
   - 修复：移入 `__main__` 块

## MEDIUM — 值得修

8. `phase_c.py:67-78` bot 检测混用 `in html`/`in html_lower` → 统一 `html_lower`
9. `phase_a.py:242` `_save_last_run_date()` 全失败时仍存 → 加 `any_success` 标志
10. `phase_h.py:146-148` 关键词标签未 `html.escape()` → 与 `domain_block` 一致
11. `phase_e.py` + DB：worker 仅 LLM、主线程写 DB 安全（`check_same_thread` 默认开启）；但 `DatabaseClient` 无任何文档/assert 阻止未来 in-worker 写入 → 至少加 docstring
12. `paper_report_generator.py:631-635` `generate_report()` 突变调用方 `papers` 列表（加 `_subdomain_labels`） → 深拷贝或传 labels
13. `publisher.py:684-704` `NatureScraper` docstring 放类属性后 → `help()` 不可见；移到顶部
14. `crossref.py:109` / `rss.py:46` / `mineru_paper_parser.py:85` `requests.Session()` 永不关闭 → 加 `close()` + context manager

## LOW — 清理

- `runner.py:115-125` `force` 已废弃，移除（保留 `run_all`）
- `phase_e.py:112-116` 未知 LLM subfield key 仍存入 DB（防 typo）
- `phase_c.py:349-351` `attempt == 0` 无条件重试 → 404 等根本性错误浪费两次
- `phase_g.py:44-48` f-string SQL 模板安全但维护陷阱（已用 `?` 参数化）
- `publisher.py:451` `download_pdf()` 每次新建 `requests.Session`（无连接复用）

## 19 假设验证汇总

| # | 假设 | 结论 | 证据 |
|---|------|------|------|
| H1 | `DAILY_PHASES` 含 `"D"` 触发 KeyError | **CONFIRMED** | runner.py:130 vs 83-93 |
| H2 | `should_skip_cr` 过滤逻辑 | REFUTED | phase_c.py:140-147 + runner 传参正确 |
| H3 | Phase E 空 scope_definition 行为 | REFUTED | phase_e.py:33-50 早 return，不处理 |
| H4 | phase_h publisher key 不匹配 | REFUTED | phase_h.py:192 与 DB column 同源 publishers.yaml |
| H5 | phase_e2 PDF 复用异常处理 | NEEDS_MORE_INFO | Linux 无强制文件锁；`Path.exists()` 对 broken symlink 返 False；风险极低 |
| H6 | `skip_phase_c_if_crossref_abstract` 散布 | CONFIRMED | 仅 OpticaScraper (publisher.py:1251) 置 True；其余继承 base (line 106) |
| H7 | first-in-group 重试不对称 | CONFIRMED (intentional) | 注释 205-207：CF 挑战需长初时；45s 合理 |
| H8 | 论文计数正则 | CONFIRMED, correct | `r'(?m)^## (?!目录)[^#]'` 处理 `## `/`### `/`## 目录` 正确 |
| H9 | Phase F 空 scope 兜底 | CONFIRMED (intentional) | phase_f.py:46-47 设计选择：无 scope = 不过滤 = 全部总结 |
| H10 | JSON 修复正则 | CONFIRMED, correct | 负回溯/负向预查处理 `\\` 正确 |
| H11 | ThreadPool + DB 线程安全 | CONFIRMED safe (fragile) | 详见 MEDIUM #11 |
| H12 | `force` 已废弃 | CONFIRMED, API clutter | runner.py:115-125 |
| H13 | bot 检测大小写不一致 | CONFIRMED | 详见 MEDIUM #8 |
| H14 | 全空解析触发 bot 检测 | CONFIRMED, correct | erratum/reply 有非空 title → 走 post-fetch 关键词检测 |
| H15 | `__unknown__` publisher 兜底 | CONFIRMED, handled | 落入 `BasePublisherScraper`（无 publisher-specific parse） |
| H16 | 非研究论文 `startswith` 检测 | CONFIRMED, correct | 关键词前缀匹配正确 |
| H17 | `mark_papers_reported` 竞态 | **CONFIRMED** | 详见 CRITICAL #2 |
| H18 | 日期格式一致性 | CONFIRMED, consistent | 均 `%Y%m%d` |
| H19 | Phase B 作者缺失标 SUCCESS | **CONFIRMED (regression)** | 详见 HIGH #3 |

## 推荐修复顺序（low risk first）

| 优先级 | 项 | 工作量 |
|--------|----|----|
| P0 | #1 runner.py 1 行删除 | 1 分钟 |
| P0 | #2 phase_g.py 改原子写 | 15 分钟 |
| P0 | #3 phase_b.py 恢复 FAILED 路径 | 10 分钟 |
| P1 | #5 config.py 默认 5-10 | 1 分钟 |
| P1 | #7 schedule_weekly.py 移入 __main__ | 5 分钟 |
| P1 | #4 + #14 所有 client 加 context manager | 30 分钟（机械） |
| P2 | #6 phase_e2.py re-indent + ruff format | 2 分钟 |
| P2 | #9 phase_a.py any_success 标志 | 10 分钟 |
| P2 | #10 phase_h.py html.escape | 2 分钟 |
| P2 | 新增 `tests/test_runner_phase_map.py` 锁 `DAILY_PHASES ⊆ phase_map.keys()` | 10 分钟（能拦住 #1 类回归） |

## Out of scope（用户明确排除）

- Web UI 安全（`src/web/app.py`）
- LLM prompt injection（理论风险，学术 pipeline 低概率）
- DOI 作文件系统路径的 null byte 等极端边界

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
| K2 | ~~`tools/convert_md_to_pdf.py` 使用 pandoc `--mathml` 路径，`\(`/`\[\]` 公式渲染空白。替代方案：`src/processors/md_to_pdf_katex.py`（KaTeX + cloakbrowser，支持公式，**实验性**，标题间距待优化）~~ | — | **已删除**（2026-07-25，公式渲染问题无法解决，统一改用 `md_to_pdf_katex.py`） |

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

# 2026-07-13 — 20260608 报告排版溢出修复（heading 层级 + CSS 兜底 + 部署脚本加固）

## 背景

用户反馈：Hugo 渲染的 20260608 报告正文不自动换行，文字宽度超出页面边界。其余 4 份报告（20260615/20260622/20260629/20260706）渲染正常。任务：定位根因 + review Hugo 部署模块。

## 根因（已确认）

20260608 报告中 SPARC_LAB 论文（#6）的 `key_setup_and_method` 字段内含 `##`（h2）子标题：

- `## 核心驱动系统`、`## 等离子体加速平台`、`## 先进诊断系统`、`## 用户束线`
- 以及 `### 高亮度SPARC光注入器`、`### 高强度FLAME激光系统` 子子标题

这些子标题在最终报告里渲染在 `### 关键方法与设置` 之下，本应是 h4/h5 层级，却以 h2 直通。

**代码路径缺陷**：`paper_report_generator.py` 中
- `main_results_and_physics` 字段经 `_process_results_markdown()` → 内部调 `_adjust_headings()` 将最低层级上移到 `base_level=4`（`####`）
- `motivation` / `method` / `take_home` 字段经 `_process_text_for_markdown()`，**不调** `_adjust_headings`，LLM 输出的 `##` 原样直通

LLM 在 `key_setup_and_method` 字段中输出的 `##` 子标题未被降级，渲染为 h2 后：
1. TOC 侧栏（`toc.html` 只匹配 `<h2>`）将这些中文子标题列为独立论文条目
2. 错位的 h2 切断了文档层级，flex 布局（`.post-content-wrapper` 260px TOC + 内容）下内容宽度计算异常
3. 长 CJK + 内联数学 `\(...\)` token 串（KaTeX 将 `\(...\)` 视为单个不可断行的 inline 元素）无法换行，溢出页面

其余 4 份报告的 LLM 输出恰好将子标题放在 `main_results_and_physics` 字段中（被 `_adjust_headings` 正确降级），故未触发。

## 修复（4 处，均已验证）

### 1. `src/processors/paper_report_generator.py`（根因修复）

`_make_markdown_section`（约 285-290 行）中 `motivation` / `method` / `take_home` 从 `_process_text_for_markdown(...)` 改为 `_process_results_markdown(..., heading_base)`。

- 现在 4 个 LLM 摘要字段（motivation/method/results/take_home）统一走 LaTeX 修复 + heading re-leveling + 换行转换
- `abstract` / `one_sentence` 仍用 `_process_text_for_markdown`（这两个字段不期望出现 heading）
- `_process_results_markdown` 名称保留（`tests/test_report.py` 导入它），仅更新 docstring 说明其已通用化
- 同步更新模块 docstring（line 9、18）与 `_make_markdown_section` docstring

### 2. `site/assets/css/extended/custom.css`（CSS 兜底）

新增：
```css
.post-content { min-width: 0; overflow-wrap: break-word; word-break: break-word; }
.post-content p, .post-content li { overflow-wrap: break-word; word-break: break-word; }
```
- `min-width: 0` 允许 flex 子项收缩到内容尺寸以下
- `overflow-wrap: break-word` 让长不可断行 CJK+数学 token 串可换行
- **未** 给 `.katex` 加 `white-space: normal`（会扭曲数学渲染）

### 3. `tools/convert_reports_to_hugo.py`（部署模块加固）

- 新增 `_validate_heading_structure(content, src_name) -> list[str]`：检测 (a) h1 数量 ≠ 1；(b) `##` 标题在两个 `##` 之间缺少 `---` 分隔符（即 20260608 缺陷模式——LLM 字段泄漏的错位子标题）。返回警告字符串，集成进 `convert_report()`，**打印警告但不阻断转换**。
- Hugo 构建 stderr 处理：成功时也输出 stderr（含 warning/info），不再仅失败时打印。
- `--all` 删除安全性：改为仅删除 front matter `source: "auto"` 的内容文件（逐文件读取 front matter），避免误删用户自写、匹配 `report_*.md` 的报告。

### 4. 回溯修复 20260608 内容

同时修补源文件 `data/reports/auto/report_20260608.md` 与 Hugo 内容 `site/content/posts/report_20260608.md`：

| 原标题 | 修复后 |
|------|------|
| `## 核心驱动系统` | `#### 核心驱动系统` |
| `### 高亮度SPARC光注入器` | `##### 高亮度SPARC光注入器` |
| `### 高强度FLAME激光系统` | `##### 高强度FLAME激光系统` |
| `## 等离子体加速平台` | `#### 等离子体加速平台` |
| `## 先进诊断系统` | `#### 先进诊断系统` |
| `## 用户束线` | `#### 用户束线` |

行尾两空格硬换行保留。

## 验证

- `python -m pytest tests/test_report.py -x -q` → 20 passed
- `hugo` 构建（`site/`）→ exit 0
- 渲染 HTML `site/public/posts/report_20260608/index.html`：48 个 h2（47 论文 + 目录），错位子标题全部降为 `<h4>`，grep 确认无 `<h2...id="核心驱动系统"` 等
- `_validate_heading_structure` 合成坏输入测试：输出警告 `疑似错位的 ## 子标题 (缺少 --- 分隔符)`；修复后输入无警告
- 转换脚本对修复后的 20260608 dry-run：无警告

## 经验教训

- **字段间处理不一致是隐蔽 bug 源**：4 个 LLM 摘要字段本应同质，却因历史原因走两条不同处理路径。统一处理路径后根因消失。
- **防御性 CSS 不可省**：即便上游 heading 层级正确，长 CJK + KaTeX 内联数学 token 串仍可能溢出。`overflow-wrap: break-word` + `min-width: 0` 是 flex 布局下渲染 CJK 学术内容的必要兜底。
- **部署脚本应做结构校验**：`convert_reports_to_hugo.py` 此前只做格式转换，不校验 heading 层级。新增的 `_validate_heading_structure` 在转换时打印警告，能在 LLM 再次输出错位标题时及早暴露，而非等到渲染后人工发现。
- **`--all` 删除范围应收敛**：原实现按 glob 删除 `report_*.md`，可能误伤用户自写报告。改为按 front matter `source` 字段过滤后，仅清理自动报告。

# 2026-07-13 — 回退自定义 Hugo 模板，改用 PaperMod 原生布局

## 背景

前一轮修复（heading re-leveling + CSS 兜底 + 内容回溯修补）后，用户反馈 20260608 报告排版溢出仍未解决。用户判定自定义 flex 侧栏布局是根因，决定回退到 PaperMod 原生样式，不再自定义目录与宽度。

## 变更

### 1. 删除自定义文章模板

- 删除 `site/layouts/single.html`（自定义 flex 侧栏模板：`div.post-content-wrapper` + `aside.toc-container` + `div.post-content`）
- 回退到主题原生 `site/themes/PaperMod/layouts/single.html`：TOC 作为可折叠 `<details class="toc">` 渲染在正文上方，正文为简单块级布局（无 flex）

### 2. 删除自定义 TOC 组件

- 删除 `site/layouts/partials/toc.html`（自定义 h2-only 匹配 + 排除 `## 目录` + scroll-spy JS）
- 回退到主题原生 `site/themes/PaperMod/layouts/_partials/toc.html`：匹配全部 `<h[1-6]>` 生成嵌套目录树，支持 `UseHugoToc` 与 `TocOpen` 参数

### 3. 精简 custom.css

`site/assets/css/extended/custom.css` 移除：
- `body:has(.post-single) .main { --main-width: 1100px; }`（文章页加宽）
- `.post-content-wrapper` flex 容器及全部子规则
- `.toc-container` 侧栏样式（sticky / scroll-spy / scrollbar / 响应式折叠）
- `.post-content { min-width: 0; ... }`（flex 子项收缩，块级布局下无意义）

仅保留一条不可见兜底：
```css
.post-content p, .post-content li { overflow-wrap: break-word; word-break: break-word; }
```
PaperMod 原生 CSS 只对 `pre code` 设了 `word-break`，段落文本没有。此规则不改变视觉样式，仅防止长 CJK + KaTeX 内联数学 token 串溢出。

### 4. 保留项

- `site/layouts/list.html` — 卡片摘要 `.Description` 优先（与溢出无关，用户未要求回退）
- `site/layouts/partials/extend_head.html` — KaTeX 数学渲染脚本（必需）
- `hugo.yaml` 的 `ShowToc: true` — 原生 TOC 全局启用
- 每报告 front matter 的 `ShowToc: true` / `TocOpen: true` — 原生 TOC 显示并默认展开

## 验证

- `hugo --cleanDestinationDir` → exit 0
- 编译 CSS `stylesheet.*.css` 中 `post-content-wrapper` / `toc-container` / `--main-width:1100px` 全部为 0 匹配（自定义布局彻底移除）
- 原生 `.post-content{margin:30px 0}` 块级布局生效
- 原生 `<details class="toc">` 已渲染在 20260608 报告正文上方
- `overflow-wrap:break-word` / `word-break:break-word` 仍在编译 CSS 中（兜底保留）
- 20260608 报告 48 个 h2（47 论文 + 目录），错位子标题仍为 h4（前一轮内容修补保持）

## 经验教训

- **flex 侧栏布局对长 CJK + 数学 token 不友好**：flex 容器中子项的 `min-content` 宽度由最长不可断行 token 决定，即便设 `min-width:0`，KaTeX 渲染后的 inline 元素仍可能撑破容器。块级布局下正文独占全宽，问题自然消失。
- **优先用主题原生能力**：PaperMod 自带可折叠 TOC + 合理的 `--main-width`，自定义侧栏与加宽虽美观但引入了原生不存在的布局风险。回退原生是更稳健的工程选择。
- **不可见兜底 CSS 可保留**：`overflow-wrap` 不改变视觉样式，只防止溢出，与"使用原生样式"不冲突。

## 20260713 报告生成缺陷修复（07-14）

### 背景

用户反馈 20260713 报告存在 4 项需修复缺陷（超长公式与简版报告经用户决策跳过）。

### 1. Cambridge 摘要 URL 误用

**根因**：`CambridgeScraper.parse_page()`（`src/sources/publisher.py`）盲信 `citation_abstract` meta 标签。部分 Cambridge 文章（hpl.2026.10180、hpl.2026.10183）该标签内容为首版 PDF 图片 URL（`//static.cambridge.org/content/id/.../firstPage-pdf-xxx.jpg`），直接采用导致报告摘要变成一串链接。

**修复**：新增 `CambridgeScraper._validate_cambridge_abstract` 类方法 + `_ABSTRACT_URL_PATTERN` 正则。若内容以 `//`、`http(s)://` 开头，或以图片/PDF 扩展名结尾，视为无效链接置空并记 warning 日志。

### 2. 字面量 `\n` 未转换（第 1 篇主要结果字段）

**根因**：LLM 在 JSON Output 模式下偶尔输出 `\\n`（双反斜杠+n），`json.loads` 解码为字面量 `\n`（反斜杠+n 两个字符）而非真实换行。`_process_results_markdown` 按 `'\n'` 切行时整段仍是一行，内部 `##` 标题不在行首，`_adjust_headings` 的 `^#{1,6}` 正则失配，标题未被重定级，内容"变成一团"。

**修复**：新增 `_convert_literal_newlines`（`paper_report_generator.py`），用正则 `r'\\n(?![a-zA-Z])'` 将字面量 `\n`（后不跟字母）转为真实换行。负向先行断言保护 LaTeX 命令 `\nabla`、`\neq`、`\nu`、`\newline` 等不被破坏。在 `_process_text_for_markdown` 与 `_process_results_markdown` 中于 `_fix_latex_backslashes_for_display` 之后、`_adjust_headings`/`split` 之前调用。

### 3. 相关方向标签错配

**根因**：`_build_subdomain_labels()`（`paper_report_generator.py`）基于 description 子串匹配生成标签。`plasma_physics` 描述含"控制"（"等离子体通道形成与控制"）→ 命中 `if '控制' in desc: labels[key] = '加速器控制与AI'` → 错配。`advanced_technology` 同样命中。DB subfields 正确，仅显示标签错。

**修复**：废弃子串匹配，改用固定 `_SUBDOMAIN_LABEL_MAP` 按 subdomain key 直接查表：
```
acceleration → 加速与后加速
plasma_physics → 等离子体物理与诊断
beam_applications → 束流诊断与辐照
advanced_technology → 束流传输与等离子体光学
laser_wakefield_acceleration → 尾场加速
```
未在表中的 key 回退为 key 本身。新增子领域只需在映射表补一行。

### 4. Hugo PaperMod TOC 层级

**根因**：用户澄清指 Hugo PaperMod 渲染后的侧边目录收录了论文内部子标题（h3/h4），希望只保留到论文标题（h2）层级。

**修复**：`site/hugo.yaml` 的 `markup` 节新增 `tableOfContents: {startLevel: 2, endLevel: 2, ordered: false}`，限定 TOC 仅收录 h2。

### 测试

- `test_process_results_markdown_literal_newline`：字面量 `\n` 转换 + 标题重定级
- `test_convert_literal_newlines_preserves_latex`：LaTeX 命令保护
- `test_cambridge_scraper_abstract_url_rejected`：URL 伪摘要拒绝
- `test_build_subdomain_labels_known`：`advanced_technology` 标签更新为"束流传输与等离子体光学"
- 全套 144 pytest 通过

### 经验教训

- **不要盲信 meta 标签内容语义**：`citation_abstract` 名字暗示摘要文本，但 Cambridge 部分页面实际存放图片 URL。外部数据源的内容语义需校验，不能仅凭标签名假设。
- **JSON 转义边界陷阱**：LLM JSON Output 模式下换行符的转义层级（`\\n` → 字面量 `\n` vs 真实换行）易混淆，处理时需显式规范化，且注意保护同形 LaTeX 命令。
- **子串匹配标签是脆弱设计**：description 文本会同时包含多方向关键词，贪婪子串匹配必然产生歧义。key→label 固定映射表无歧义、可维护、新增成本极低，应优先采用。

---

# 2026-07-24 — 移除 Phase D（embedding 余弦相似度）

**摘要**：Phase D（sentence-transformers 余弦相似度）从流水线中**整体移除**——不再作为阶段、不再写 DB 列、不再读 `sub_domains_embedding` 配置。

**移除原因**：
- 默认 `SKIP_PHASE_D = True`（永远跳过），整段代码已是死代码
- `get_papers_sorted_by_semantic()` 全代码库零调用方；`papers.html` 不渲染 `semantic_similarity_score`/`semantic_best_subdomain`
- 唯一声明用途（"WebUI Papers 页排序参考"）与代码现状脱节
- 论文量级小（每轮 ~200-400 篇），DeepSeek API 成本极低，语义分门禁无收益

**变更范围**（7 个独立 commit）：

| # | 类型 | 提交信息 | 简述 |
|---|------|---------|------|
| 1 | `refactor` | remove Phase D semantic filter from pipeline | 删 `phase_d.py`、`SemanticFilter` 类、Runner/Config/WebUI/templates 中 D 阶段注册；移除 6 个 SemanticFilter 测试 |
| 2 | `refactor` | drop semantic columns and methods from DB layer | DB 5 列 + 2 方法 + 白名单 + 阶段统计 + `get_papers()` SELECT；新增 `tools/migrate_db_v3.py`（已删除 2026-07-25，迁移已落地） |
| 3 | `refactor` | remove Phase D reset hooks | 删 `reset-semantic` 子命令 + `cmd_reset_semantic()` + `SEMANTIC_RESET`；移除 5 列重置 SQL |
| 4 | `refactor` | remove sub_domains_embedding from keyword config | 删 `CFG.SEMANTIC_MODEL_PATH`、`CFG.SKIP_PHASE_D`、`load_keywords()` 中 `sub_domains_embedding` 字段；移除 `keywords.yaml.example` 配置段 + `settings.yaml.example` `D:` 行 + `semantic:` 节 |
| 5 | `test` | remove last Phase D test references | 移除 `test_relevance.py` 中 `sub_domains_embedding` dict 字段 + 注释行 |
| 6a | `docs` | remove Phase D references from design.md and README.md | 全部清完（design 架构图、Schema 段、决策章节、字段表、Reset 段；README 字段表、reset 示例、架构图、目录树） |
| 6b | `docs` | append 2026-07-24 移除 Phase D 备注 to tasks.md | **本节**，保留所有历史记录（30+ 处）作事实档案 |
| 7 | — | （无 commit） | 项目根无 `requirements.txt` / `pyproject.toml` / `setup.*` / `Pipfile`，全代码库零 `import sentence_transformers`，无可改文件 — 详见下方"commit 7 取消说明" |

**commit 7 取消说明**：
- 期望操作：从 `requirements.txt` 等依赖文件中移除 `sentence-transformers`
- 实际结果：项目无标准依赖声明文件，且全代码库零 `import sentence_transformers`（commit 1 已删 `src/processors/paper_relevance.py` 中两处 import），唯一引用是 `tools/migrate_db_v3.py:12`（已删）的 docstring 文字描述（**非 import**）
- 验证命令：`grep -rE "import sentence_transformers|sentence-transformers" --include="*.{py,sh,toml,txt,cfg,yml,yaml,env*,json}"` 返回空
- 历史背景：Phase D 长期依赖 `sentence-transformers` 是隐式（运行环境提供），从未在仓库中显式声明。删除 Phase D 代码后无需修改任何依赖文件
- 后续建议：如未来项目需要集中声明依赖（与 Phase D 无关），可独立创建 `requirements.txt` 记录 deepseek、playwright、pyyaml 等

**验证**：153/153 测试全过；DB 5 列已从 `data/papers.db` 物理删除（v3 schema migration 完成）；WebUI 路由 /papers?sort=created|published 不再读 semantic 字段；reset_pipeline --help 不再有 `reset-semantic` 子命令。

**保留历史记录**：本文件上方所有提到 Phase D / `semantic_filter_*` / `sub_domains_embedding` / `SemanticFilter` / `sentence-transformers` / `bge-base-en-v1.5` 的行/段/章节均**完整保留**——它们是事实档案（实施记录、调试经验、API 文档），与最终代码解耦后仍有参考价值。删除它们会让"git log 之前的 commits"失去上下文。

---

### ⚠️ 2026-07-24 review 阶段发现：移除不完整（CRITICAL #1）

后续 `2026-07-24 — Pipeline 全面 Code Review` 阶段，Oracle 审计发现上述 commit 1 (`remove Phase D semantic filter from pipeline`) **只删除了 `phase_map` 中的 "D" 注册，但漏删 `runner.py:130` 的 `DAILY_PHASES` 常量**。

**当前状态**（review 时验证）：
- `src/pipeline/runner.py:130` 的 `DAILY_PHASES = ["A-RSS", "A-CR", "B", "C", "D", "E", "E2", "F"]` 仍包含 "D"
- `phase_map`（同文件 ~83-93）已无 "D" 键
- `tools/schedule_daily.py` 每日调度执行 `run_daily()` → `run_phases(phase_list=DAILY_PHASES)` → 遇到 "D" 时 `func, args, enabled = phase_map[key]` 抛 `KeyError: "D"`
- `tools/schedule_weekly.py` 走 `run_pipeline()` → `run_phases(phase_list=DEFAULT_PHASES)`，**未受影响**（`DEFAULT_PHASES` 也不含 "D"）

**影响**：每日定时任务会**立即崩溃**，从未在该提交后成功跑过一次日调度（推测）。该 bug 与本节"验证 153/153 测试全过"**不矛盾**——测试只覆盖了模块导入、阶段注册表，未对 `DAILY_PHASES` 列表本身做断言。

**修复方向**（已记入下方 review 段 CRITICAL #1 跟进项）：删除 `DAILY_PHASES` 中的 "D" 字符串。无需补回归测试（CRITICAL 列表加一条防御性测试即可）。

---

# 2026-07-24 — Review 三大 Critical/High 修复落地

**触发**：上方「2026-07-24 — Pipeline 全面 Code Review」节定位 2 CRITICAL + 1 HIGH 等问题后，立即调度 @fixer 落地修复最高风险 3 项。

**方法**：3 个独立 @fixer 并行（`fix-1`/`fix-2`/`fix-3`），分别写 runner.py / phase_g.py / phase_b.py，互不重叠。@oracle 全局调度（`ora-1`）保留以便后续审查。

**修复成果**（4 文件修改 + 2 新测试文件，**157/157 pytest 通过**）：

| 修复 | 文件 | 变更 | 新增测试 |
|------|------|------|----------|
| **CRITICAL #1** | `src/pipeline/runner.py:130,137` | 移除 `DAILY_PHASES` 中的 `"D"` + 同步 docstring | `tests/test_runner_phase_map.py`（2 测试：`DAILY_PHASES`/`WEEKLY_PHASES` 均为 `phase_map.keys()` 子集） |
| **CRITICAL #2** | `src/pipeline/phase_g.py:112-141` | 原子写入：`.tmp` → `replace()` → 再 `mark_papers_reported()`（与 phase_a.py 智能回溯一致的原子模式） | （无新测试，行为变更无破坏性回归） |
| **HIGH #3** | `src/pipeline/phase_b.py:44-69` | 作者缺失：原「仅 warning + 标 SUCCESS」改为「warning + 标 FAILED」，与 tasks.md 2026-05-23 / design.md 契约对齐 | `tests/test_phase_b_authors.py`（2 测试：作者空 → FAILED；作者非空 → SUCCESS） |

**测试覆盖**：
- `pytest tests/` → **157 passed**（修改前 153 + 新增 4）
- `test_runner_phase_map.py`：防御性回归测试锁死 `DAILY_PHASES ⊆ phase_map.keys()`，未来再有人删阶段忘了改调度常量会立即失败
- `test_phase_b_authors.py`：HIGH #3 双向覆盖（FAILED 路径 + SUCCESS 路径），防止「过修」

**改动统计**：`git diff --stat`：
```
docs/tasks.md           | 124 +++++++++++++++++++++++++++++++++++++++++++++++-
src/pipeline/phase_b.py |  32 ++++++++-----
src/pipeline/phase_g.py |  12 +++--
src/pipeline/runner.py  |   4 +-
4 files changed, 154 insertions(+), 18 deletions(-)
```

**未修问题**（HIGH 4-7 / MEDIUM 8-14 / LOW 15-19）见上方 review 节，按"价值/成本"排序等待后续专项处理。

**教训**：
- 自动化测试应覆盖**配置/常量**与**实际运行路径**的双向一致（如 `DAILY_PHASES ⊆ phase_map.keys()`），否则 153 测试全过仍可能漏掉 CRITICAL #1
- "写文件后再标 DB"是流水线类系统的通用原子模式，CRITICAL #2 的修复与 `phase_a.py` `_save_last_run_date` 的现有模式一致——**全代码库应统一采用 tmp+rename+mark 模式**
- 设计文档 (`design.md` / `tasks.md` 2026-05-23 节) 与代码的漂移需要 review 类工作定期发现，HIGH #3 即源于此

---

# 2026-07-24 — Review 跟进批 #2（HIGH #4/6/7 + MEDIUM 8-14）

**触发**：上方 review 章节中剩余 HIGH（#4 #6 #7）+ 全部 MEDIUM（#8-#14）共 10 个修复点。用户已明确：
- HIGH #5 `LLM_CONCURRENT_MAX=100` **保留默认**（用户说明：deepseek-flash 上限 2000 并发，deepseek-pro 上限 500 并发，100 远低于限流线，无实际风险）
- LOW 5 项**暂不处理**

**方法**：3 个 @fixer 并行处理（`fix-1` 复用 DB session，`fix-4` 复用 phase_* 上下文，`fix-5` 复用 sources/processors 上下文），互不重叠文件。

## 修复清单

| 级别 | # | 位置 | 修复要点 | 测试 |
|------|---|------|----------|------|
| **HIGH** | #4 | `src/db/database.py` | `DatabaseClient` 加 `close()` / `__enter__` / `__exit__`（idempotent，conn=None 后再 close 安全） | `tests/test_database_client_context.py` (3 测试) |
| **HIGH** | #6 | `src/pipeline/phase_e2.py:107-129` | `for paper in lazy_pending:` 循环体从 20 空格缩进改为 16 空格（一层 4 空格） | 无（视觉/工具化修复） |
| **HIGH** | #7 | `tools/schedule_weekly.py` | 模块级 `mkdir`+`basicConfig`+`_check_mineru_token()` 移入 `if __name__ == "__main__":` 块；提取 `_setup_logging_and_dirs()` 函数 | 无（导入副作用修复） |
| **MEDIUM** | #8 | `src/pipeline/phase_c.py:67-69` | bot 检测前 3 项 `in html` 改为 `in html_lower`（大小写一致） | 无（行为收敛修复） |
| **MEDIUM** | #9 | `src/pipeline/phase_a.py` | `_save_last_run_date()` 加 `any_success` 守卫，全失败时不再延长回溯窗口 | 无（状态机修复） |
| **MEDIUM** | #10 | `src/pipeline/phase_h.py:148` | 关键词标签 `{kw}` → `{html.escape(kw)}`；新增 `import html` | 无（XSS/HTML 完整性） |
| **MEDIUM** | #11 | `src/pipeline/phase_e.py` | `ThreadPoolExecutor` 上方新增 5 行线程安全契约注释（DB 写入仅主线程） | 无（文档化） |
| **MEDIUM** | #12 | `src/processors/paper_report_generator.py` | `generate_report()` 改 copy-on-write（`{**paper, ...}`），不再突变调用方 list | 无（语义修复） |
| **MEDIUM** | #13 | `src/sources/publisher.py:684-704` | `NatureScraper` docstring 移到类体首句；`help()` 现在可见 | 无（API 文档化） |
| **MEDIUM** | #14 | `crossref.py:109` / `rss.py:46` / `mineru_paper_parser.py:85` | 三个 client 类加 `close()` / `__enter__` / `__exit__`（idempotent） | 无（资源泄漏修复） |

## 测试覆盖

- `pytest tests/ -q` → **160 passed in 23.96s**
- 本批新测试：**3**（`test_database_client_context.py`）
- 累计三轮修复后新测试：**7**（`test_runner_phase_map.py` 2 + `test_phase_b_authors.py` 2 + `test_database_client_context.py` 3）
- **无回归**

## 改动统计

```
docs/tasks.md                            | 162 +++++++++++++++++++++++++++++-
src/db/database.py                       |  18 ++++
src/pipeline/phase_a.py                  |   9 +-
src/pipeline/phase_b.py                  |  32 +++---
src/pipeline/phase_c.py                  |   6 +-
src/pipeline/phase_e.py                  |   5 +
src/pipeline/phase_e2.py                 |  40 ++++----
src/pipeline/phase_g.py                  |  12 ++-
src/pipeline/phase_h.py                  |   3 +-
src/pipeline/runner.py                   |   4 +-
src/processors/mineru_paper_parser.py    |  14 +++
src/processors/paper_report_generator.py |   5 +-
src/sources/crossref.py                  |  16 +++
src/sources/publisher.py                 |  10 +-
src/sources/rss.py                       |  12 +++
tools/schedule_weekly.py                 |  28 +++---
16 files changed, 312 insertions(+), 64 deletions(-)
```

## 显式未修（用户决定）

| # | 位置 | 原因 |
|---|------|------|
| HIGH #5 | `CFG.LLM_CONCURRENT_MAX=100` | 用户澄清：deepseek-flash 上限 2000 / deepseek-pro 上限 500，100 远低于限流线，**无实际风险** |
| LOW #1-5 | runner.force 废弃 / phase_e subfield 白名单 / phase_c 404 不重试 / phase_g f-string / publisher.py Session 复用 | 用户指示**暂不处理** |

## 教训

- **资源拥有者必加 context manager**：DatabaseClient (#4) + 3 个 Session (#14) 一起补齐，**未来所有 client 类创建时即应自动实现**（写入 lint 规则或 design.md 强制规范）
- **模块级副作用 = 隐藏 bug**：`schedule_weekly.py` (#7) 与早期 `config.py` 的 `_check_mineru_token()` 同根——**任何 `tools/*.py` 入口脚本**都应在 `if __name__ == "__main__":` 块内执行 I/O / logging
- **线程安全是契约问题，不是类型问题**：`phase_e.py` (#11) 的注释是给未来维护者的提示，比加锁更实际
- **copy-on-write 优于 in-place mutation**：`generate_report()` (#12) 修了一个易被忽视的接口污染，调用方再无需担心传入 list 被改写


