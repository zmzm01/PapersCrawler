# 使用手册

> 本文面向实际使用者。架构细节见 [`docs/design.md`](design.md)，历史记录见 [`docs/archive/`](archive/)。

## 目录

- [安装与首次运行](#安装与首次运行)
- [CLI 与调度](#cli-与调度)
- [WebUI](#webui)
- [典型工作流](#典型工作流)
- [关键词管理与效果评估](#关键词管理与效果评估)
- [配置](#配置)
- [工具索引](#工具索引)
- [输出与数据](#输出与数据)
- [测试与故障排查](#测试与故障排查)

## 安装与首次运行

```bash
python -m pip install -r requirements.txt
cp .env.example .env

# 编辑 .env，至少填写：
# CROSSREF_MAILTO / MINERU_TOKEN / DEEPSEEK_API_KEY
vim configs/keywords.yaml

# 桌面环境
python tools/run_pipeline.py --all

# 无头服务器（Phase C 需要显示器）
xvfb-run -a python tools/run_pipeline.py --all
```

报告默认写入 `data/reports/auto/`。如果只想查看执行计划，增加 `--dry-run`；dry-run 不重置数据库、不运行阶段、不发送 ntfy。

## CLI 与调度

### 推荐入口

`python tools/run_pipeline.py` 是统一入口：

| 参数 | 阶段 | 说明 |
|---|---|---|
| `--daily` | A-RSS/A-CR/B/C/E/E2/E3/F | 日常发现、抓取、全文判断和总结 |
| `--weekly` | G/H | 报告生成和邮件推送 |
| `--all` | A-RSS/A-CR/B/C/E/E2/E3/F/G/H | 忽略 `skip_phases` 全流程执行 |
| `--phases A,B,C` | 指定阶段 | 只运行列出的阶段 |

不传模式时等效于 `--all`。`--all` 会临时覆盖阶段 skip flag，执行所有阶段；发生阶段错误或初始化错误时返回退出码 1，成功返回 0。旧的 `src/main.py` 仅保留兼容用途；生产调度统一使用此入口。

### 常用参数

| 参数 | 作用 |
|---|---|
| `--dry-run` | 只显示计划 |
| `--reset-publisher` / `--no-reset-publisher` | 是否自动重置 Publisher failed |
| `--reset-mineru` / `--no-reset-mineru` | 是否自动重置 MinerU failed/skipped |
| `--reset-relevance` / `--no-reset-relevance` | 是否自动重置 E/E3 failed |
| `--log-level LEVEL` | DEBUG/INFO/WARNING/ERROR |

### 阶段开关

在 `configs/settings.yaml` 中设置：

```yaml
skip_phases:
  A_RSS: false
  A_CR: false
  B: false
  C: false
  E: false
  E2: false
  E3: false
  F: false
  G: false
  H: true
```

`--daily` 和 `--weekly` 遵守这些开关；`--all` 忽略它们。每阶段处理上限由 `pipeline.max_papers_per_phase` 控制，按整个阶段计算而不是按 Publisher 重置，0 表示不限制。

### Cron

```cron
0 2 * * * cd /path/to/PapersCrawler && ./run_daily.sh >> /var/log/paperscrawler-daily.log 2>&1
0 20 * * 7 cd /path/to/PapersCrawler && ./run_weekly.sh >> /var/log/paperscrawler-weekly.log 2>&1
```

服务器建议使用 `Asia/Shanghai` 时区。包装脚本已经设置项目目录、PYTHONPATH 和 cron 所需的 PATH。

### 日志和 ntfy

日志按自然日写入 `data/logs/PaperCrawler-YYYY-MM-DD.log`，单日文件达到 10MB
后最多保留一个 `.1` 备份，默认保留最近 14 天。旧的 `data/PaperCrawler.log`
是历史聚合日志，不再作为新入口的写入目标。设置 `LOG_LEVEL=INFO` 可减少输出。

不需要手工 `cat`/`grep` 时，直接运行日志统计工具：

```bash
python tools/log_report.py                         # 今天的 WARNING/ERROR
python tools/log_report.py --days 7                 # 最近 7 天汇总
python tools/log_report.py --level ERROR --limit 50 # 只看错误明细
python tools/log_report.py --contains "MinerU"      # 按关键词筛选
python tools/log_report.py --summary-only           # 只看总数、来源和高频消息
python tools/log_report.py --json > /tmp/log.json   # 给脚本继续处理
```

默认输出包括级别总数、产生问题最多的模块、重复消息和最近明细；终端会自动使用
颜色突出错误，重定向或 `--json` 时不会混入颜色控制符。

ntfy 敏感项位于 `.env`：

```dotenv
NTFY_BASE_URL=https://ntfy.sh
NTFY_TOPIC=your_private_topic
NTFY_TOKEN=tk_your_access_token
```

非敏感项位于 `configs/settings.yaml`：

```yaml
ntfy:
  enabled: true
  timeout_seconds: 10
  title: "PapersCrawler 运行汇总"
  priority: default
```

每次非 dry-run 运行最多发送一条通知，正文面向 ntfy Web App 使用较宽松的 Markdown 布局，依次展示运行概览、阶段执行、E 初筛/E3 正文终审的状态与 A/B/C/D 分类统计、F 总结状态，以及问题和连续失败提醒。问题会按
`C 抓取失败`、`E2 PDF/MinerU失败`、`LLM失败`、`通知失败`、`其他问题` 等类别合并计数，并展示脱敏示例。连续失败提醒只针对下载审计表中同一个 DOI 的 E2 PDF/MinerU 失败：连续 2 天提示关注，连续 3 天标记“需人工干预”；不同 DOI 不会合并计算。通知正文使用 ntfy Web App 支持的标题、粗体/斜体、列表、引用块、行内代码和分隔线，不使用表格或 `<details>` 等扩展语法。通知不发送原始长错误堆栈；详细信息仍查看 `python tools/log_report.py` 和 `data/raw/page/error/`。通知失败不会改变流水线结果。

## WebUI

启动：

```bash
LOG_LEVEL=INFO PYTHONPATH=src uvicorn src.web.app:app --host 127.0.0.1 --port 8080
```

上述命令适合临时调试。日常运行推荐使用 systemd，使 WebUI 脱离终端、开机启动并在异常退出后自动重启。
WebUI 本身不启动浏览器或流水线，因此不需要 `xvfb-run`；无头服务器只有运行包含 Phase C 的流水线时才需要虚拟显示器。

### systemd 管理 WebUI

项目提供了用户级 service 模板：
[`deploy/systemd/paperscrawler-web.service`](../deploy/systemd/paperscrawler-web.service)。
它默认使用 `/path/to/paperscrawler-venv/bin/python`，安装前请按实际环境修改
`ExecStart` 的 Python 解释器路径。模板默认监听 `127.0.0.1:8080`、使用单 worker、`INFO` 日志，
并在进程异常退出后 5 秒重启。

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/paperscrawler-web.service ~/.config/systemd/user/

# 如果 Python 环境路径不同，编辑 ExecStart 后再执行以下命令
systemctl --user daemon-reload
systemctl --user enable --now paperscrawler-web.service
systemctl --user status paperscrawler-web.service
```

查看实时日志：

```bash
journalctl --user -u paperscrawler-web.service -f
```

应用仍会将日志写入 `data/logs/PaperCrawler-YYYY-MM-DD.log`；systemd/journald 额外保存标准输出，
适合查看启动失败和进程重启原因。常用维护命令：

```bash
systemctl --user restart paperscrawler-web.service
systemctl --user stop paperscrawler-web.service
systemctl --user disable paperscrawler-web.service
```

如果希望用户未登录时也自动启动，需要在主机上启用 lingering：

```bash
sudo loginctl enable-linger "$USER"
```

局域网访问建议让 Nginx 等反向代理监听外部地址，再转发到 `127.0.0.1:8080`，并由代理层提供
TLS、认证、限速和访问源限制。临时调试才可将 uvicorn 改为 `--host 0.0.0.0`；当前 WebUI
不适合直接暴露公网。systemd 只管理 WebUI 进程，日常/每周流水线仍由下面的 cron 任务负责。

| 路由 | 功能 |
|---|---|
| `/` | 302 跳转到 Dashboard |
| `/dashboard` | 阶段状态、统计卡片和 7 日趋势 |
| `/papers` | 论文列表、A/B 分类、已总结筛选、排序和分页 |
| `/report` | 查看和下载已有报告 |
| `/relevance-review` | 人工审核队列 |
| `/relevance-review/{doi}` | 单篇审核详情 |

审核队列只显示 E3 已完成全文终审的论文：`llm_relevance_status=success` 且 `llm_relevance_basis=fulltext`。默认优先未审核 B/中置信度、初筛/终审分歧和 A/中置信度记录。

审核提交会向 `relevance_reviews` 追加 A/B/C/D/uncertain、备注、审核人和 LLM 快照，不覆盖 `papers` 原始结果。审核 API 只接受 E3 全文终审成功的论文；`uncertain` 会按数据库 schema 保存为小写。

## 典型工作流

### 修改研究范围后重判

```bash
vim configs/keywords.yaml
python tools/reset_pipeline.py reset-relevance --all
python tools/run_pipeline.py --phases E,E2,E3,F
```

只重判指定 DOI：

```bash
python tools/reset_pipeline.py reset-relevance --dois DOI1,DOI2
```

### Publisher 抓取失败后重试

```bash
python tools/reset_pipeline.py reset-publisher --publisher aps
python tools/run_pipeline.py --all
```

Cloudflare/Radware 或早期导航失败时先查看 `data/raw/page/error/` 和同一时间段的 `data/logs/PaperCrawler-YYYY-MM-DD.log`，再调整 `publisher.page_delay_*`、`publisher.proxy` 或挑战页 reload 参数。错误快照是诊断辅助；即使浏览器在页面 HTML 生成前失败，日志也应保留原始导航异常，而不是被快照保存错误覆盖。若 fallback 浏览器已经关闭，快照保存会只使用此前缓存的 HTML，不再调用已关闭页面的 `content()`。

Phase C 的常规浏览器重试全部失败后，还可以配置一个末级代理 fallback。该 fallback 会用新浏览器上下文重试当前论文一次；成功会写入正常成功状态，失败仍按原错误流程落库。代理 URL 为空时关闭：

```yaml
publisher:
  fallback_proxy_url: "http://127.0.0.1:7890"
```

该配置只影响 Phase C，不改变正常抓取路径；代理失效时会增加一次失败尝试，但不会阻塞其他论文。

### PDF 下载失败或需要手动导入

```bash
python tools/import_local_pdf.py --doi <DOI> --pdf /path/to/paper.pdf
python tools/run_pipeline.py --phases E2,E3,F
```

导入工具会先校验并复制 PDF，再将对应 DOI 的 `mineru_parse_status` 设为 `pending`、清空旧错误和日期，并立即提交事务；正常输出应包含 `数据库状态已更新 ... 影响行数=1`。导入的 PDF 会被 E2 校验并直接复用，即使数据库中的 `pdf_url` 为空也不再触发下载失败；只有没有合法本地 PDF 时才要求网络 PDF URL。
Optica 通常需要代理；APS 会尝试改写跨域 PDF 链接。失败尝试会消耗当日 E2 配额。

### 预览报告

```bash
python tools/preview_report.py --scope all --output /tmp/preview.md
python tools/preview_report.py --scope week --date 2026-08-20 --output /tmp/week.md
python tools/preview_report.py --scope today --output /tmp/today.md --no-explainer
# 只生成截止日期以前入库的论文（不含 2026-08-17 当天）
python tools/preview_report.py --scope all --before-date 2026-08-17 \
  --output data/reports/user/report_before_20260817.md
# 同时同步到公开站点（默认不公开预览报告）
python tools/preview_report.py --scope all --before-date 2026-08-17 \
  --output data/reports/user/report_before_20260817.md --export-public
```

`--before-date` 使用论文的 `created_date`（入库日期）做严格上限，格式为
`YYYY-MM-DD`，截止日当天及之后的论文都会排除。它可以与 `--scope week` 或
`--scope today` 组合使用。每次预览都会在 Markdown 旁生成同名的
`.public.json` 结构化快照；只有指定 `--export-public` 才会同步到公开站点。
预览不标记数据库，不影响下次 Phase G。

### 发送指定报告

```bash
python tools/send_report.py --report report_YYYYMMDD.md
python tools/send_report.py --report report_YYYYMMDD.md --recipients a@example.com,b@example.com
python tools/send_report.py --report report_YYYYMMDD.md --dry-run
```

## 关键词管理与效果评估

`configs/keywords.yaml` 将研究范围拆成四层：`context_gates` 做多义词语境消歧，
`irrelevant_fields` 做主题级排除，`scope_definition` 描述领域化分类，
`keyword_catalog` 独立维护术语、别名和目标子域。关键词目录只提供召回提示和审计
证据，单个字符串命中不会直接把论文判为相关。

当前目录覆盖 plasma lens、discharged capillary、plasma channel、bunch plasma
wakefield、烧蚀/毛细管/等离子体通道诊断、FLASH 流体动力学、闪烁体/塑料闪烁体、
可变形镜、库仑力、发射度、电光晶体、active plasma focusing、EMP、
post-acceleration 和 PIC simulation 等兴趣点。新增兴趣点时添加一个稳定 `id`，
填写 `terms` 别名，并映射到现有 `scope_definition` 子域。

先检查目录本身：

```bash
python3 tools/keyword_audit.py
python3 tools/keyword_audit.py --json
```

也可以用抓取出的标题/摘要 JSONL 观察实际覆盖。每行至少包含 `title` 和 `abstract`：

```bash
python3 tools/keyword_audit.py --corpus /path/to/title_abstract.jsonl
```

### Relevance benchmark

仓库提供 `benchmarks/relevance_gold.jsonl` 作为可扩展的人工标注样本，包含明确相关
的 A/B、邻近的 C 和困难负例 D。预测文件使用同样的 JSONL 格式，但将
`gold_category` 换成 `predicted_category`，并保留相同的 `id`：

```json
{"id":"plasma-lens-001","predicted_category":"A"}
```

评分同时输出四分类准确率、混淆矩阵以及 A/B（报告保留）对 C/D 的 precision、recall
和 F1：

```bash
python3 tools/evaluate_relevance.py \
  --gold benchmarks/relevance_gold.jsonl \
  --predictions /path/to/predictions.jsonl
```

已有人工审核记录时，可直接评估最新审核结论与最终 LLM 分类：

```bash
python3 tools/evaluate_relevance.py --db data/papers.db
```

建议每次修改研究范围后重跑固定 benchmark，并定期从 WebUI 人工审核队列补充边界案例。
重点关注 A/B recall（不要漏掉真正想看的论文）、A/B precision（不要浪费全文配额）
和 B↔D、A↔B 错误；当前数据库没有人工审核样本时，工具会显示样本数为 0。

## 配置

完整可复制模板：[`configs/settings.yaml.example`](../configs/settings.yaml.example)。

### `.env`

| 变量 | 用途 |
|---|---|
| `CROSSREF_MAILTO` | CrossRef API 联系邮箱 |
| `MINERU_TOKEN` | MinerU Token |
| `DEEPSEEK_API_KEY` | 默认 LLM API Key |
| `SMTP_HOST/PORT/USE_TLS` | SMTP 连接 |
| `SMTP_USERNAME/PASSWORD` | SMTP 凭据 |
| `SMTP_FROM_ADDR` | 发件人 |
| `SMTP_TO_ADDRS` | 逗号分隔的回退收件人 |
| `NTFY_BASE_URL/TOPIC/TOKEN` | ntfy 连接和凭据 |

### `configs/settings.yaml`

主要配置组：

| 组 | 关键字段 |
|---|---|
| `skip_phases` | A_RSS、A_CR、B、C、E、E2、E3、F、G、H |
| `llm` | base_url、relevance、fulltext_relevance、summary、concurrent_max、retry |
| `fulltext_download` | daily_max、publisher_daily_max、delay_min/max_seconds |
| `pipeline` | CrossRef 回溯、处理上限、Nature 过滤、非研究过滤、解释页开关 |
| `publisher` | 页面延迟、失败熔断、challenge reload、常规 proxy、末级 fallback proxy URL |
| `email` | 模板名 |
| `formula_fix` | skip、force、concurrent_max、llm |
| `ntfy` | enabled、timeout、title、priority |

#### LLM 协议与模型配置

`llm.base_url` 是服务基础地址；每个角色可以通过 `protocol` 选择请求协议：

- `openai_chat`：发送到 `/chat/completions`，兼容 OpenAI、DeepSeek 及多数网关。
- `openai_responses`：发送到 `/responses`，使用 Responses API 的 `instructions`、`input`、`text.format` 和 `output` 响应结构；适用于 OpenCode Zen 的 Muse Spark Contributor。
- `anthropic_messages`：发送到 `/messages`，使用 `x-api-key`、`anthropic-version` 和 Anthropic Messages 响应格式。

配置支持全局 `llm.protocol`，也支持在 `relevance`、`fulltext_relevance`、`summary` 中分别覆写。下面是 OpenCode Go 使用 MiniMax M3 的示例：

```yaml
llm:
  base_url: https://opencode.ai/zen/go/v1
  relevance:
    protocol: openai_chat
    model: mimo-v2.5
  summary:
    protocol: openai_chat
    model: minimax-m3
    thinking: disabled
    max_tokens: 65536

formula_fix:
  skip: false
  force: false
  concurrent_max: 10
  llm:
    protocol: openai_chat
    model: mimo-v2.5
    thinking: disabled
    max_tokens: 4096
    timeout: 120
```

程序内部先构造统一的 `model/messages/thinking` 请求，再由协议适配层转换。Responses 协议会把 system prompt 放到 `instructions`，把用户消息放到 `input`，并将 JSON 模式转换为 `text.format.type=json_object`；返回结果从 `output_text` 或 `output` 文本块读取。Messages 协议不发送 OpenAI 专用的 `response_format`，结构化输出依靠 Prompt 中的“只输出合法 JSON”约束。对于需要严格 JSON 的总结，建议使用 `thinking: disabled`，避免思考内容与 JSON 混在同一输出中；Responses 如需控制推理，可配置 `reasoning_effort: low|medium|high`。

FormulaFixer 使用 `formula_fix.llm` 的独立配置，不会自动使用 `relevance` 或 `summary` 的模型；`formula_fix.concurrent_max` 也不会占用 `llm.concurrent_max`。它在总结响应解析成功后异步修复各篇论文，修复失败会保留原文本。若 FormulaFixer 服务不稳定，可先设 `formula_fix.skip: true` 完成 Phase F 总结。

FormulaFixer 之前的历史结果也可以单独修复，不必重新调用 Phase F：

```bash
PYTHONPATH=src /path/to/paperscrawler-venv/bin/python \
  tools/fix_summary_formulas.py --dry-run

PYTHONPATH=src /path/to/paperscrawler-venv/bin/python \
  tools/fix_summary_formulas.py
```

第一条只检测，不调用 LLM、不写数据库；第二条会按 `formula_fix.concurrent_max` 并发处理，
确认后写回。若只处理单篇，可加 `--doi DOI`；若要无条件重新处理非占位文本，加 `--force`。
工具也会写回本地可确定修复的 JSON 伪转义和 `$...$`，即使 FormulaFixer 请求失败也不会丢失这部分修复。

模型返回值在标准 JSON 解析前会自动提取 ` ```json ... ``` ` 围栏或前后夹杂说明中的 JSON 对象，并兼容常见的裸 LaTeX 反斜杠和字符串内英文引号。若仍解析失败，查看日志中的 `Invalid escape` 或 `LLM non-JSON response`，该篇不会污染其他论文的状态。

如果使用 Muse Spark Contributor，summary 角色改为 `protocol: openai_responses`、模型 `muse-spark-1.2-contributor`；endpoint 为 `https://opencode.ai/zen/go/v1/responses`。若只写 `base_url: https://opencode.ai/zen/go/v1`，程序会按角色自动追加对应端点。若日志出现 HTTP 403，先确认当前角色、模型和 endpoint 是否匹配；若 HTTP 200 后出现 `Invalid escape`，则查看 JSON 解析兼容层日志。

### 期刊和研究范围

`configs/publishers.yaml` 定义期刊的 `id`、`name`、`publisher`、`rss`、`issn`、`enabled`、`rss_enabled` 和 `cr_enabled`。

`configs/keywords.yaml` 使用四层结构：

- `context_gates`：词义消歧。
- `irrelevant_fields`：主题级黑名单。
- `keyword_catalog`：可审计术语、别名和子域映射。
- `scope_definition`：正类子域、描述和主题列表。

### Prompt

`configs/prompts/relevance.yaml`、`summary.yaml`、`fix.yaml` 分别对应 E/E3、F 和公式修复。文件缺失时使用 `src/config.py` 的内置后备值。

`summary.yaml` 的 Phase F 输出格式为 schema v3：`main_results_and_physics` 是带稳定
`key` 的数组，每项分别填写 `title`、`finding`、`evidence` 和
`physical_interpretation`；`limitations` 是独立的带 key 数组，每项填写局限、影响和
`basis`（`explicit`/`inferred`）。`study_type` 和 `basis` 仅用于 JSON 的机器分析，不会
渲染到人读报告；报告中的每条局限把影响接在同一行，不再嵌套第二层无序列表。动机、方法
和要点也使用固定字段 key。不要在这些字段中写 Markdown 标题或把多个结果合并成一段话。
缺失信息写 `未提供`；没有正文依据的局限输出空数组，不要生成“局限：未提供”的占位项。
如果 `method`、`setup_and_parameters` 和 `analysis_or_model` 全部缺少实质内容，Phase F
会把该响应标记为失败并等待重试。

### 邮件收件人

`data/email.yaml`：

```yaml
recipients:
  - email: user@example.com
    name: "User"
    enabled: true
```

文件缺失、为空或解析失败时回退 `.env` 的 `SMTP_TO_ADDRS`。

### `journal_overrides.json`

`data/journal_overrides.json` 是可选期刊覆写。每日/每周调度不读取；`tools/run_pipeline.py --all` 的 Phase A 会读取，缺少字段时回退 `publishers.yaml`。

## 工具索引

| 工具 | 用途 |
|---|---|
| `run_pipeline.py` | 推荐流水线入口 |
| `reset_pipeline.py` | 重置 CrossRef、Publisher、MinerU、相关性、总结或报告状态 |
| `preview_report.py` | 生成不改数据库的 JSON + Markdown 报告预览，可选公开导出 |
| `log_report.py` | 统计、筛选和查看 WARNING/ERROR 日志 |
| `keyword_audit.py` | 校验关键词目录并统计语料中的术语命中 |
| `evaluate_relevance.py` | 计算 benchmark 或人工审核集的相关性指标 |
| `send_report.py` | 发送指定报告 |
| `import_local_pdf.py` | 导入本地 PDF 到 E2 队列 |
| `fix_summary_formulas.py` | 修复总结中的 LaTeX |
| `dedup_doi_case.py` | 清理历史 DOI 大小写重复 |
| `convert_reports_to_hugo.py` | 转换并部署 Hugo 报告 |
| `export_public_reports.py` | 导出静态站点 JSON |
| `deploy_report_site.py` | 构建并可选上传独立 Astro 报告站点 |

根目录的 `run_daily.sh` 和 `run_weekly.sh` 是 cron 包装脚本，内部调用
`run_pipeline.py`；它们不是独立的流水线实现。已删除旧的
`schedule_daily.py` 和 `schedule_weekly.py`，不要再使用旧路径。
包装脚本默认调用 PATH 中的 `python`，conda/venv 环境可设置
`PAPERSCRAWLER_PYTHON=/path/to/env/bin/python`；daily 脚本检测到 `xvfb-run` 时会自动使用它。

### `run_pipeline.py`

推荐的唯一流水线入口：

```bash
python tools/run_pipeline.py --daily       # A-F
python tools/run_pipeline.py --weekly      # G-H
python tools/run_pipeline.py --all         # A-H，忽略 skip_phases
python tools/run_pipeline.py --phases E,E2,E3,F
python tools/run_pipeline.py --daily --dry-run
```

论文列表 `/papers?has_summary=true` 或页面上的“已生成总结”筛选会在数据库查询和分页计数阶段同时生效。

### `preview_report.py`

生成不修改数据库的 JSON + Markdown 报告。默认只筛选已完成总结的 A/B 论文，
也会包含已经出现在旧报告中的论文：

```bash
python tools/preview_report.py --scope all --output /tmp/report.md
python tools/preview_report.py --scope all \
  --before-date 2026-08-17 \
  --output data/reports/user/report_before_20260817.md
python tools/preview_report.py --scope all \
  --output data/reports/user/report.md --export-public
```

每次都会生成同名 `.public.json`。`--before-date` 使用 `created_date` 做严格上限，
截止日当天不包含；`--export-public` 会把自动报告目录和当前预览目录一起同步到
公开导出目录。可用 `--export-root PATH` 覆盖导出目录。

### `export_public_reports.py`

将 JSON sidecar 导出到静态站点数据目录，不重新运行 LLM，也不修改数据库：

```bash
python tools/export_public_reports.py \
  --out /path/to/MySite/.generated/reports

# 多个来源目录可以重复 --source
python tools/export_public_reports.py \
  --out /path/to/MySite/.generated/reports \
  --source data/reports/auto \
  --source data/reports/user
```

输出为 `papers/index.json` 和按报告 ID 命名的 JSON 文件。默认来源是
`data/reports/auto/`；默认导出根目录是 `PUBLIC_REPORT_EXPORT_DIR`，未设置时为
项目同级 `MySite/.generated/reports`。

### 独立 Astro 报告站点

旧 Hugo 站点暂时保留，仍可使用：

```bash
python tools/convert_reports_to_hugo.py --all --hugo
```

新站点源码位于 `report-site/`，不依赖 `../MySite`。它使用 Node.js/npm，当前服务器通过
`/path/to/nvm` 管理 Node；非交互 shell 需要显式加载 nvm：

```bash
cd report-site
. /path/to/nvm/nvm.sh
nvm use default
npm ci
npm run check
npm run build
```

构建前需要将公开 JSON 导出到 Astro 的生成数据目录：

```bash
cd /path/to/PapersCrawler
python3 tools/export_public_reports.py --out report-site/src/data/reports
```

一键构建并检查 Cloudflare 上传参数，但不上传：

```bash
python3 tools/deploy_report_site.py --dry-run
```

正式 Direct Upload 需要设置以下环境变量：

```bash
export CLOUDFLARE_ACCOUNT_ID="..."
export CLOUDFLARE_API_TOKEN="..."
export CLOUDFLARE_PAGES_PROJECT="paperscrawler-reports"
python3 tools/deploy_report_site.py
```

API Token 只应授予 Cloudflare Pages 写权限，不要写入仓库或普通配置文件。部署脚本默认
加载 `NVM_DIR=/path/to/nvm`，也可通过 `NVM_DIR` 覆盖。`--branch NAME` 用于上传预览
分支，未指定时上传生产部署。当前该命令不会修改 Hugo 或 `gh-pages`。

### `reset_pipeline.py`

重置失败状态或使论文重新进入报告队列。子命令：

```text
reset-crossref  reset-publisher  reset-mineru
reset-relevance  reset-summary  reset-report
```

所有子命令都要求交互确认。`reset-report --today` 可恢复当天误标记为已报告的论文；
`reset-relevance` 支持 `--all`、`--categories A,B,C` 或 `--dois DOI1,DOI2`；
`reset-summary` 支持 `--dois DOI1,DOI2` 精确重置异常总结。

单篇总结修复/重跑示例：

```bash
PYTHONPATH=src /path/to/paperscrawler-venv/bin/python \
  tools/reset_pipeline.py reset-summary --dois 10.1063/5.0335213

PYTHONPATH=src /path/to/paperscrawler-venv/bin/python \
  tools/run_pipeline.py --phases F
```

`reset-summary --dois` 只清空指定论文的 F 状态，不影响全文和相关性结果；随后 Phase F
只会消费 pending 的目标论文。修改总结 Prompt 后确实需要全部重生成时才使用
`reset-summary --all`，这会重新消耗所有论文的 LLM 配额。

### 其他工具

| 工具 | 常用命令 |
|---|---|
| `send_report.py` | `python tools/send_report.py --report report_YYYYMMDD.md [--dry-run]` |
| `import_local_pdf.py` | `python tools/import_local_pdf.py --doi <DOI> --pdf <PATH>` |
| `fix_summary_formulas.py` | `python tools/fix_summary_formulas.py [--doi DOI] [--publisher NAME] [--dry-run] [--force]` |
| `dedup_doi_case.py` | `python tools/dedup_doi_case.py --dry-run`；确认后去掉 `--dry-run` 执行一次性迁移 |
| `convert_reports_to_hugo.py` | `python tools/convert_reports_to_hugo.py --all --hugo --deploy`；可用 `--dry-run` 预览 |

## 输出与数据

| 路径 | 内容 |
|---|---|
| `data/papers.db` | SQLite 主库 |
| `data/logs/` | 按日期分文件的运行日志，默认保留 14 天 |
| `data/reports/auto/` | 自动日报、解释页、public sidecar |
| `data/reports/user/` | 历史用户报告归档及 JSON sidecar |
| `data/mineru_output/` | PDF、MinerU 输出和 `full.md` |
| `data/raw/` | RSS、页面和错误快照 |
| `data/session_cached/` | Publisher 浏览器上下文 |

报告资格：E3 `fulltext` + A/B + F summary success + 尚未 `report_date`。

摘要清洗：RSS、CrossRef 和 Publisher 摘要进入数据库前会统一解码 HTML/XML 实体、移除
控制字符并压缩空白；数据库初始化会幂等修复已有标题/摘要，报告快照生成时还会清洗一次历史数据。因此 IOP 摘要中的
`&#xD;` 不应出现在新报告中。公开 JSON 的报告封装 `schemaVersion` 为 2，论文分析的
`summarySchemaVersion` 为 3；`content.papers[].summary` 是可供程序直接消费的唯一规范总结，
`sections` 仅保留为兼容旧消费者的同结构分节映射。

## 测试与故障排查

### 测试

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-branch --cov-report=term-missing
bash tests/real/run_all.sh
```

覆盖率命令使用仓库根目录的 `.coveragerc`：统计 `src/` 的行和分支覆盖，显示未覆盖行，
并以 80% 作为失败门槛。T1/T2 测试通过 mock 隔离浏览器、LLM、MinerU、SMTP 和 CrossRef；
T3 会消耗真实 API/SMTP 配额，谨慎运行。当前覆盖率报告用于发现重试、异常和配置边界，
不把真实服务连通性误当作离线覆盖。

### 流水线不动

检查当天的 `data/logs/PaperCrawler-YYYY-MM-DD.log`、`.env` Key、
`configs/settings.yaml` 中的 `skip_phases`，确认没有把所有阶段设为 true。

LLM 返回 HTTP 400 时，先看日志中的响应正文；如果提示 `invalid thinking.type`，将对应角色的 `thinking` 改为 `disabled` 或 `adaptive`，不要把 OpenAI Chat 的 `enabled` 直接当作 Messages 参数。

### 摘要仍有实体或乱码

先确认数据库中的摘要是否含有 `&#xD;`、`&amp;#xD;` 或不可见控制字符。重新运行
Phase B/C 会用统一清洗链路覆盖有效摘要；仅重新生成报告时，ReportSnapshot 也会在
展示层清洗历史值。若是科学符号（如 `×`、`◦`）仍存在，这是预期行为，不应一律删除。

### 总结报告层级重复

新运行的 Phase F 会先将响应规范化为 schema v3，报告只渲染固定字段、结果列表和局限列表。旧的
`llm_summary_result` 即使仍是 Markdown 字符串，也会在读取时转换；如需将历史论文重新
落库为 v2，可使用 `reset-summary` 后重跑 `--phases F`（会重新调用 LLM）。

### 总结内容过少或公式乱码

Phase F 会把只有一句话、没有具体结果的 JSON 响应标记为 failed；下次运行会自动重试。
历史 success 结果先运行 `fix_summary_formulas.py --dry-run` 查看候选，再去掉
`--dry-run` 执行修复。若内容本身不完整（例如除一句话外全部为 `未提供`），使用
`reset-summary --dois DOI` 后运行 `tools/run_pipeline.py --phases F`，不要只依赖公式修复。

### SMTP 失败

检查 SMTP 凭据、`data/email.yaml` 中是否有启用收件人、Phase H 是否被跳过，并查看日志和垃圾邮件箱。

### WebUI 启动失败

```bash
pip install -r requirements.txt
lsof -i :8080
LOG_LEVEL=INFO PYTHONPATH=src uvicorn src.web.app:app --host 127.0.0.1 --port 8081
```

如果由 systemd 管理，先检查服务状态和 journald：

```bash
systemctl --user status paperscrawler-web.service
journalctl --user -u paperscrawler-web.service -n 100 --no-pager
```

常见原因是 `ExecStart` 使用了不存在的 Python 路径、8080 端口已被占用，或 `.env`/配置文件权限不允许
服务用户读取。修改 unit 后需要重新执行 `systemctl --user daemon-reload`，再重启服务。

### 数据库锁

避免在 CLI 大量写入期间提交人工审核；WAL 只能减少冲突，不能消除并发写等待。

### Hugo 部署（旧站点）

检查 `hugo`、`ghp-import` 和 cron PATH，然后运行：

```bash
python tools/convert_reports_to_hugo.py --all --hugo --deploy
```

Hugo 是当前旧站点链路，后续迁移完成后再废除。新 Astro 站点使用上面的
`tools/deploy_report_site.py`，两条链路暂时并行。

## 相关文档

- [`README.md`](../README.md)
- [`docs/design.md`](design.md)
- [`docs/tasks.md`](tasks.md)
- [`docs/archive/`](archive/)
