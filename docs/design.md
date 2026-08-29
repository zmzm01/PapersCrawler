# 项目需求与架构设计

> 本文只描述当前有效的需求、架构和设计决策。历史实施过程见 [`docs/archive/design-legacy.md`](archive/design-legacy.md)。

## 目标与边界

PapersCrawler 自动追踪配置的学术期刊，经过元数据补全、Publisher 页面抓取、两阶段相关性判断、PDF/MinerU 解析和 LLM 总结后，生成日报并通过邮件或静态站点发布。

- 研究范围由 `configs/keywords.yaml` 定义。
- 全文获取依赖使用者已有的机构访问权限，不提供绕过付费墙的功能。
- 单篇论文失败不得阻塞同阶段其他论文。
- 所有阶段状态持久化到 SQLite，支持断点续跑和精确重置。
- WebUI 是监控、报告阅览和人工相关性审核工作台，不负责启动流水线或编辑配置。

## 项目结构

```text
configs/                 YAML 配置和 Prompt
data/                    SQLite、日志、缓存、报告和 MinerU 输出
docs/                    当前文档
docs/archive/            历史文档和完整流水账
deploy/systemd/          WebUI 的 systemd 用户级服务模板
src/
  config.py              配置加载与 CFG
  keyword_catalog.py     术语目录匹配与校验
  common.py              共享模型和异常
  db/database.py        SQLite CRUD、迁移和审核表
  sources/               RSS、CrossRef、Publisher 抓取
  pipeline/              Phase A/B/C/E/E2/E3/F/G/H
  processors/            LLM、MinerU、报告、邮件和通知
  web/                   FastAPI WebUI
tools/
  run_pipeline.py       推荐 CLI/cron 入口
  reset_pipeline.py     状态重置
  preview_report.py     不污染数据库的报告预览
  log_report.py         日志统计、筛选和查看
  keyword_audit.py      关键词目录校验与语料覆盖审计
  evaluate_relevance.py 相关性 benchmark 评分
  send_report.py        指定报告邮件发送
  import_local_pdf.py   手动导入 PDF
  export_public_reports.py 公开 JSON 导出
report-site/
  src/                  PapersCrawler 独立 Astro 报告站点源码
  scripts/sync-reports.mjs 构建前同步并校验报告 JSON
  package.json          Astro/Wrangler 构建依赖
```

## 流水线

| 阶段 | 作用 | 主要输出 |
|---|---|---|
| A-RSS / A-CR | RSS 和 CrossRef 双源发现 | DOI、标题、链接、发现来源 |
| B | CrossRef 元数据补全 | 作者、日期、期刊、摘要 |
| C | Publisher 页面抓取 | 页面摘要、正文链接、PDF 链接 |
| E | 标题/摘要高召回初筛 | `relevance_screen_*` |
| E2 | 受持久化配额保护的 PDF 下载和 MinerU 解析 | `mineru_*`、`full.md` |
| E3 | 正文相关性终审 | `llm_relevance_*` |
| F | LLM 结构化总结 | `llm_summary_*` |
| G | 自动报告和解释页 | `data/reports/auto/` |
| H | SMTP 邮件推送 | 邮件及附件 |

只有 E3 正文终审成功、类别为 A/B、依据为 `fulltext`，并且 F 总结成功的论文才具备进入自动报告的资格。

### 元数据文本清洗

RSS、CrossRef 和 Publisher 页面都经过 `common.clean_extracted_text()` 再进入数据库或
LLM。清洗顺序是 HTML/XML 实体解码（包括双重编码的 `&amp;#xD;`）、Unicode NFC
规范化、不可见控制字符移除、断行连字符合并和空白压缩。这样 IOP 页面中的字面量
`&#xD;` 不会进入摘要、相关性 Prompt 或报告；数据库初始化还会运行幂等的
`normalize_metadata_text()` 迁移，修复已有标题/摘要。ReportSnapshot 仍会再做一次清洗，
兼容迁移前生成的内存数据或外部导入数据。科学符号（例如 `×`、`◦`）不作为噪声删除。

## 数据模型

### `papers` 主表

每篇论文一行，保存元数据和各阶段状态。常用字段：

- 标识与元数据：`id`、`doi`、`title`、`abstract`、`journal`、`publisher`、作者、日期和 URL。
- 发现来源：`discovery_source`，可为 RSS、CrossRef 或二者。
- E 初筛：`relevance_screen_status/category/confidence/reason`。
- E2：`mineru_parse_status/error/date`、`mineru_output_dir`。
- E3：`llm_relevance_status/category/confidence/reason/basis`。
- F：`llm_summary_status/error/date/result`。
- G：`report_status`、`report_date`。

状态通常为 `pending`、`success`、`failed` 或 `skipped`。新增字段通过 `DatabaseClient.init_db_papers()` 渐进迁移。

### 辅助表和文件

| 名称 | 用途 |
|---|---|
| `fulltext_download_events` | 每日/每出版社 PDF 尝试配额审计，失败也占额 |
| `relevance_reviews` | 追加式人工审核记录，保存结论、备注、审核人及 LLM 快照 |
| `skipped_dois` | 永久跳过的非研究文章 DOI |
| `data/email.yaml` | Phase H 收件人配置 |
| `data/mineru_output/.../full.md` | MinerU 全文，供 E3/F/人工审核读取 |

人工审核不覆盖 `papers` 中的 LLM 原始结果；同一 DOI 的最新审核记录按最大 `id` 作为当前审核结果。

## 配置模型

配置来源分工如下：

| 文件 | 内容 |
|---|---|
| `.env` | API Key、MinerU Token、CrossRef 邮箱、SMTP 和 ntfy topic/token |
| `configs/settings.yaml` | 阶段开关、模型、配额、延迟、重试、邮件、通知 |
| `configs/publishers.yaml` | 期刊、RSS、ISSN、Publisher 和启用状态 |
| `configs/keywords.yaml` | `context_gates`、`irrelevant_fields`、`keyword_catalog`、`scope_definition` |
| `configs/prompts/*.yaml` | relevance、summary、formula fix Prompt |
| `data/email.yaml` | 收件人及 `enabled` 状态 |
| `data/journal_overrides.json` | 可选期刊覆写，仅 `--all` 的 Phase A 读取 |

阶段开关位于 `configs/settings.yaml` 的 `skip_phases`。`--daily` / `--weekly` 遵守开关，`--all` 使用 `force=True` 忽略开关；强制运行期间只临时覆盖运行时 flag，阶段结束后恢复原配置。
`pipeline.max_papers_per_phase` 是每个阶段的全局上限，不按 Publisher 重置。Phase F 的正常队列只查询全文终审成功且最终为 A/B 的论文，避免把 C/D 的历史 pending 标记反复扫描。
运行时消费者统一通过 `from config import CFG` 读取可热加载配置。

### LLM 协议适配

LLM 调用在 `common.call_llm_api_with_retry` 统一执行重试、熔断和响应提取。处理器只构造内部规范化的 `model/messages/thinking` 请求；配置中的每个角色通过 `protocol` 选择线协议：

- `openai_chat` 将请求发送到 `/chat/completions`，保留 OpenAI 风格的 `choices[0].message.content` 解析。
- `openai_responses` 将 system 消息转换为 `instructions`、其余消息转换为 `input`，发送到 `/responses`，并从 `output_text` 或 `output[].content[].text` 提取回答；`response_format` 转换为 Responses API 的 `text.format`。
- `anthropic_messages` 将 system 消息拆为顶层 `system`，发送 `max_tokens` 和 `messages` 到 `/messages`，并从 `content` 文本块提取回答。

协议适配层负责请求头（Bearer 或 `x-api-key`）、端点和响应结构转换，因此模型名称不会散落在代码中形成特殊分支。Responses 与 Messages 的思考参数不直接发送 OpenAI Chat 的 `thinking` 字段；Responses 可选用 `reasoning_effort`。Anthropic Messages 不支持 OpenAI 的 `response_format`，结构化任务继续由 Prompt 约束 JSON；思考块只在提取文本时被忽略。严格 JSON 的任务默认使用 `thinking: disabled`，而需要推理时可按协议配置。

LLM 文本进入 JSON 解析前还会做一次边界清洗：提取 Markdown ` ```json ... ``` ` 或前后夹杂说明中的 JSON 对象，修复常见的裸 LaTeX 反斜杠和字符串内英文引号，再交给标准 JSON 解析器。该兼容层只修复明确的格式问题，无法替代模型输出校验；解析失败仍会按单篇错误隔离并保留 pending/failed 状态。

### FormulaFixer 独立配置与并发

FormulaFixer 是 Phase F 总结后的可选文本后处理，不复用相关性角色的模型配置。`formula_fix.llm` 独立配置协议、模型、思考模式、输出上限和超时，`formula_fix.concurrent_max` 独立限制公式修复线程数。Phase F 的总结请求完成后，每篇论文的 FormulaFixer 任务进入独立线程池；每个任务使用自己的 HTTP Session，避免在线程间共享连接对象。公式修复失败只回退该文本节点，不影响结构化总结写入。

若本机可运行 `report-site/scripts/render-markdown-katex.mjs`（Node.js + `marked` + `katex`），FormulaFixer 还会对已正确包裹的公式执行 KaTeX 校验。`formula_fix.max_repair_rounds` 定义每个字段最多几轮“校验 → 带错误的 LLM 修复 → 再校验”，默认一轮；只有最终通过时才替换原文本，超过轮数则保留原文本。Node 或依赖不可用时该验证器静默降级，保留原有启发式和 LLM 修复行为。KaTeX 支持的 `cases`、`matrix`、`aligned` 等复杂环境允许保留；不把 KaTeX 的子集限制误判为完整 LaTeX 语义校验。

该拆分避免公式修复占用总结并发池，也避免主线程逐篇等待所有修复请求。默认仍通过 `needs_fix()` 跳过无需修复的文本；如果只需要先完成总结，可将 `formula_fix.skip` 设为 `true`。

### 关键词目录与效果评估

`scope_definition` 是给 LLM 的自然语言分类本体，描述研究对象、A/B 边界和排除语境；`keyword_catalog` 是可审计的术语目录，每个条目包含稳定 `id`、术语/别名 `terms`、目标 `subdomains` 和可选说明。目录用于检查兴趣点是否配置、为 Prompt 提供召回提示、扩展正文证据词汇，以及在标题/摘要语料上统计实际命中。

目录命中不是相关性结论。Phase E 仍依据标题/摘要、语境门控和领域定义做高召回 LLM 初筛，Phase E3 再用正文作最终判定。效果评估使用小型人工标注 JSONL benchmark，覆盖 A/B 正例、C 邻近例和 D 困难负例，同时报告四分类混淆矩阵和 A/B 对 C/D 的 precision、recall、F1。WebUI 的人工审核记录也可作为持续增长的真实评估集，且不覆盖原始 LLM 结果。

## 关键设计决策

### 1. 两阶段相关性判断

E 只用标题和摘要做高召回筛选。A/B/C 和低置信 D 进入 E2/E3；高/中置信 D 直接终止。E3 使用全文作最终判断，避免摘要降级入报。

### 2. 关键词不是单独的过滤器

术语目录与领域化筛选分离。这样 `plasma`、`diagnostics`、`EMP` 等多义词不会因为一次字符串命中直接进入报告；目录负责可见性和审计，`context_gates`、`irrelevant_fields` 和 `scope_definition` 负责语境、主贡献和分类。

### 3. 全文下载配额

E2 使用 `fulltext_download_events` 通过事务占位，按 Asia/Shanghai 自然日限制总尝试数和单 Publisher 尝试数。同一 DOI 当天最多尝试一次，失败也计入配额。

### 4. 错误隔离与重试

- Phase 级异常由 runner 收集并继续后续阶段。
- 单篇异常写入对应 error 字段，不影响同阶段其他论文。
- CLI daily 默认重置 Publisher、MinerU 和 LLM 相关性的 failed 状态。
- Publisher 支持 Cloudflare challenge reload、失败熔断、持久化浏览器上下文和 HTML 错误快照；常规抓取重试耗尽后，可用 `publisher.fallback_proxy_url` 启动独立代理上下文再尝试一次。`BasePublisherScraper` 在构造时初始化空 HTML，错误快照优先使用缓存内容，并在页面/事件循环已关闭时跳过 live content 读取，确保导航在生成页面内容前失败时不会被二次快照异常遮蔽。`import_local_pdf.py` 将 PDF 落盘和 MinerU 状态重置作为一次明确提交的数据库操作。
- LLM 请求支持指数退避和 circuit breaker。
- LLM 支持按角色切换 OpenAI Chat Completions 与 Anthropic Messages 协议；HTTP 4xx 错误会保留有限长度的服务端响应正文，便于定位网关参数不兼容。

### 5. 报告分离

报告先由数据库行构造统一的 ReportSnapshot，原子写入版本化 JSON，再从同一份内存结构渲染 Markdown；这样 Markdown 不再是结构化数据的唯一载体。自动报告写入 `data/reports/auto/` 并标记已报告；预览报告由 `tools/preview_report.py` 写入用户指定路径且不改数据库，同时生成同名 JSON sidecar。预览可按 `created_date` 使用 `--before-date YYYY-MM-DD` 设置严格日期上限，截止日当天不包含在内；只有显式指定 `--export-public` 才会同步到公开站点。`data/reports/user/` 保留历史用户报告及其 JSON 快照，当前 WebUI 只查看和下载。

### 6. Phase F 总结 schema

Phase F 将 LLM 返回值规范化为 `summary_schema` v3 后再写入
`llm_summary_result`。顶层固定为 `one_sentence`、`motivation_and_goal`、
`key_setup_and_method`、`main_results_and_physics`、`limitations` 和
`take_home_message`；动机、方法和要点使用固定 key，主要结果和局限使用带唯一 `key`
的数组元素。结果分别保存 `finding`、`evidence` 与 `physical_interpretation`，局限保存
`limitation`、`impact` 与 `basis`；其中 `study_type` 和 `basis` 是机器元数据，只保留在
结构化 JSON，不显示在面向读者的报告中。报告将每个局限渲染为单层条目，并把 `impact`
接在同一条目中，不再生成局限下的二级无序列表，也不依赖 LLM 生成 Markdown 标题。旧版
字符串/Markdown 总结在读取时自动转换，缺少实质局限的占位记录会被丢弃。公开 JSON 同时提供
`summarySchemaVersion: 3` 和结构化 `summary`，方便后续分析。报告封装版本独立为
`schemaVersion: 2`；`content.papers[].summary` 是唯一规范的机器可读总结，旧版
`sections` 仅作为兼容投影保留。

Phase F 在写入前执行两级保护：`repair_llm_text_artifacts()` 恢复 JSON 解码时被误解释为
退格、换页、制表符或回车的常见 LaTeX 命令，并把 `$...$` / `$$...$$` 转为报告统一的
公式分隔符；`summary_quality_issues()` 检查一句话、方法/设置是否有实质内容、至少一个具体
结果和最低内容量。只通过 JSON 解析但方法部分为空或实质为空的响应会标记为 failed，等待
下一次重试，不会进入报告。历史 success
记录可用 `tools/fix_summary_formulas.py` 递归修复，复杂 LaTeX 环境仍交给 FormulaFixer
的独立模型处理。

### 静态 KaTeX/Prince PDF 链路

报告 PDF 的规范渲染链路为 `Markdown → marked HTML → 静态 KaTeX HTML/MathML → Prince PDF`。
Node 脚本先以唯一占位符保护 `\(...\)` 与 `\[...\]`，防止 Markdown 解析把公式中的下划线或
反斜杠当作文本标记；`marked` 解析其余内容后，KaTeX 以 `throwOnError: true` 阻断真实语法错误，
以 `strict: "warn"` 放行兼容性警告后渲染并替换占位符。静态 HTML 同目录包含复制的 KaTeX CSS/字体，Prince 无需执行 JavaScript 或
联网。公式错误会阻止 PDF 生成，并通过同一渲染脚本供 FormulaFixer 收集为 LLM 修复上下文。

`tools/convert_md_to_pdf.py` 是用户入口。Prince 为首选排版后端；其免费版水印是可接受的已知
展示限制。旧的 cloakbrowser/Chrome 打印模块继续保留，仅作为历史兼容工具，不再是推荐路径。

### 7. 配置与入口隔离

生产入口统一为 `tools/run_pipeline.py`：

- `--daily`：A-RSS/A-CR/B/C/E/E2/E3/F。
- `--weekly`：G/H。
- `--all`：全部阶段，忽略阶段开关。
- `--phases A,B,...`：按需运行指定阶段。
- 旧的 `src/main.py` 仅保留兼容用途；`tools/schedule_daily.py` 和 `tools/schedule_weekly.py` 已删除，生产调度统一使用 `tools/run_pipeline.py`。

## WebUI 架构

WebUI 使用 FastAPI + Jinja2，当前页面如下：

| 页面 | 路由 | 权限/作用 |
|---|---|---|
| Dashboard | `/dashboard` | 只读状态、阶段统计、7 日趋势 |
| Papers | `/papers` | 只读论文列表、类别筛选、已总结筛选和分页 |
| Report | `/report` | 只读报告查看和下载 |
| Relevance Review | `/relevance-review` | 审核队列和筛选 |
| Review Detail | `/relevance-review/{doi}` | 查看摘要/全文/LLM 结果并提交审核 |

唯一写入端点是 `POST /api/relevance-reviews`，只接受固定决策值和长度受限的备注/审核人字段；审核目标必须是 E3 全文终审成功的记录，`uncertain` 以 schema 规定的小写形式保存。

安全边界：

- 报告下载使用 `resolve()` 和 `relative_to()` 防路径遍历。
- 人工审核全文只允许从数据库记录的 `data/` 相对路径读取 `full.md`。
- 报告 Markdown 在浏览器端经过 DOMPurify 清理。
- 响应包含 nosniff、clickjacking 和权限策略响应头。
- 生产环境应由 Nginx 提供 TLS、认证、限速和访问源限制；不要直接暴露公网。

### WebUI 运行方式

WebUI 是独立的 FastAPI 常驻进程，不负责启动流水线或浏览器抓取。开发/临时调试可以直接运行
uvicorn；生产或个人服务器部署使用 `deploy/systemd/paperscrawler-web.service` 的用户级
systemd 服务。服务默认绑定 `127.0.0.1:8080`、单 worker、`LOG_LEVEL=INFO`，异常退出后自动重启；
局域网或公网访问由反向代理提供 TLS、认证和访问控制。无头服务器的 `xvfb-run` 只属于包含
Phase C 的流水线运行，不属于 WebUI 服务。

## 报告和发布

Phase G 输出：

- `report_YYYYMMDD.public.json`：版本化、公开安全的结构化报告快照。
- `report_YYYYMMDD.md`：自动 Markdown 报告。
- `report_YYYYMMDD_explained.html`：Prompt 和判定依据解释页，可由 `pipeline.generate_explained_html` 控制。

Phase H 从 `data/email.yaml` 读取收件人，失败时回退 `.env` 的 `SMTP_TO_ADDRS`。ntfy 只在运行结束时发送一条面向 Web App 的 Markdown 汇总，按区块展示运行概览、所有阶段耗时、E/E3 相关性状态与 A/B/C/D 分类、F 总结状态、问题示例和连续失败提醒。连续失败提醒读取 `fulltext_download_events`，按同一个 DOI 的本地日期计算，仅对 E2 PDF/MinerU 失败提供连续 2/3 天提醒；不同 DOI 不合并，通知失败不影响流水线。

通知正文使用 ntfy Web App 当前支持的 Markdown 子集：标题、粗体/斜体、列表、引用块、行内代码、代码块和水平分隔线；不使用表格、HTML 或 `<details>` 等扩展。请求仍设置 `Markdown: yes` 与 `Content-Type: text/markdown`，消息上限保守保持 3500 UTF-8 bytes，以适应 ntfy 默认 4096 bytes 限制。移动端不是当前排版目标，客户端不支持 Markdown 时会看到原始标记文本。

`tools/export_public_reports.py` 将一个或多个目录中的 sidecar 导出为 `papers/index.json` 和按 ID 的 JSON 文件；不会重新调用 LLM 或修改数据库。预览报告使用 `--export-public` 时会合并自动报告目录和预览报告所在目录，避免同步预览时删除已有自动报告。

### 独立 Astro 报告站点

`report-site/` 是 PapersCrawler 自己拥有的静态报告站点，不依赖 `../MySite`。它只消费
公开报告 JSON，构建时生成报告归档、论文目录、A/B 等级、标签、链接和结构化解读。
生成数据位于 gitignored 的 `report-site/src/data/reports/`，不会进入 Git 历史。

现有 `site/` Hugo 目录和 `tools/convert_reports_to_hugo.py` 作为旧设计暂时保留；新 Astro
站点验收完成前，`run_weekly.sh` 仍按原流程发布 Hugo。

Astro 使用静态输出，不读取 SQLite、API 密钥或内部 WebUI 数据。`tools/deploy_report_site.py`
负责将自动报告导出到 Astro 数据目录、加载 nvm 中的 Node.js、构建 `report-site/dist/`，
并可选上传 Cloudflare Pages。

## 部署与运维

WebUI 使用 systemd 常驻，部署模板位于
`deploy/systemd/paperscrawler-web.service`；论文流水线仍由 cron 调用
`run_daily.sh` 和 `run_weekly.sh`。二者共享 SQLite WAL 数据库，systemd 不改变数据库并发语义，
人工审核仍应避免在流水线大量写入期间提交。

日常 cron：

```cron
0 2 * * * /path/to/PapersCrawler/run_daily.sh
0 20 * * 7 /path/to/PapersCrawler/run_weekly.sh
```

`run_daily.sh` 执行 `tools/run_pipeline.py --daily`；当前 `run_weekly.sh` 执行 `--weekly` 后继续
Hugo 部署。无头服务器运行 Phase C 需要 `xvfb-run`。Astro 站点目前通过独立命令预览或部署，
不改变现有 cron。

日志由 `src/logging_config.py` 统一配置，按自然日写入
`data/logs/PaperCrawler-YYYY-MM-DD.log`；单日文件使用 10MB 大小上限并保留一个
备份，旧日志默认保留 14 天。`LOG_LEVEL` 控制日志级别。旧的
`data/PaperCrawler.log` 仅作为历史聚合日志保留，不再写入。运维通过
`tools/log_report.py` 按日期、级别和关键词读取这些文件，避免依赖手工 grep；该工具
只读日志，不改变流水线状态。

## 测试和迁移

- T1/T2：`pytest tests/ -v`，完全离线。
- 覆盖率：`pytest tests/ --cov=src --cov-branch --cov-report=term-missing`；`.coveragerc`
  统计应用源码的行/分支覆盖，门槛为 80%。外部浏览器、LLM、MinerU、邮件和 HTTP 依赖必须
  通过 fake/mock 验证成功、重试、跳过和失败路径，不能要求 T1/T2 触网。
- T3：`bash tests/real/run_all.sh`，需要真实 API/SMTP 配置。
- SQLite 新字段由 `init_db_papers()` 自动迁移。
- 修改研究范围后使用 `reset-relevance`，不要手工直接改状态字段。

## 相关文档

- [`README.md`](../README.md)：项目首页和 Quick Start。
- [`docs/usage.md`](usage.md)：完整使用手册。
- [`docs/tasks.md`](tasks.md)：近期任务与当前上下文。
- [`docs/archive/`](archive/)：历史设计、使用手册和完整任务流水账。
