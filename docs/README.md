# PapersCrawler — 文献自动追踪与推送

自动抓取领域核心期刊文章，筛选与组内工作相关的论文，生成结构化报告并推送。

> **项目不是 Python package** — `src/` 下没有 `__init__.py`，所有 import 相对于项目根目录解析。必须从项目根目录运行。

## 快速开始

### 1. 安装依赖

```bash
pip install requests feedparser beautifulsoup4 parsel pyyaml ruamel.yaml python-dateutil
pip install python-dotenv                  # .env 密钥加载
pip install cloakbrowser "cloakbrowser[geoip]"  # 浏览器自动化
pip install sentence-transformers          # 语义相似度初筛（Phase D）
pip install pytest                         # 测试
```

### 2. 配置

**复制 `.env.example` 为 `.env`，填写密钥：**

```bash
cp .env.example .env
```

```ini
# .env — 不要提交到仓库
CROSSREF_MAILTO=your_email@example.com
MINERU_TOKEN=your_mineru_token_here
DEEPSEEK_API_KEY=sk-your-deepseek-key
```

**configs/keywords.yaml** — 填写研究领域定义（scope_definition 含子领域描述+关键词、irrelevant_fields 排除领域）：

```yaml
scope_definition:
  laser_wakefield_acceleration:
    description: "本方向关注基于等离子体的尾场加速技术..."
    topics:
      - "Laser Wakefield Acceleration (LWFA) — ..."
  laser_driven_ion_acceleration:
    description: "本方向关注利用超强激光驱动的离子加速机制..."
    topics:
      - "Target Normal Sheath Acceleration (TNSA) — ..."
irrelevant_fields:
  description: "以下领域即使出现相关关键词也应排除..."
  topics:
    - "Fusion: Tokamak, Stellarator, ICF — ..."
sub_domains_embedding:
  laser_wakefield_acceleration: >
    Plasma-based wakefield acceleration driven by intense laser pulses...
```

**SMTP 配置（可选，不配置则跳过 Phase H）：** 编辑 `.env` 文件，添加以下字段：

```ini
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your_email@qq.com
SMTP_PASSWORD=your_auth_code          # 授权码，不是邮箱密码
SMTP_FROM_ADDR=your_email@qq.com
SMTP_TO_ADDRS=colleague1@example.com,colleague2@example.com
```

> ⚠️ `.env` 包含真实密钥，**不要提交到公开仓库**。

配置自检：

```bash
python src/config.py   # 打印已加载的期刊配置
```

### 3. 运行

**完整流水线：**
```bash
# 桌面环境（有显示器）
python src/main.py

# 无图形界面服务器（Phase C 需要虚拟显示器）
xvfb-run -a python src/main.py
```

**按调度模式运行：**

| 模式 | 包含阶段 | 推荐频率 | 命令 |
|------|---------|---------|------|
| 每日 | A→F（发现到 LLM 总结） | 每天 | `python tools/schedule_daily.py` |
| 每周 | G→H（报告生成到邮件推送） | 每周一 | `python tools/schedule_weekly.py` |

```bash
# 每日运行（配合 cron：每天 2:00）
0 2 * * * cd /path/to/PapersCrawler && python tools/schedule_daily.py

# 每周运行（配合 cron：每周一 9:00）
0 9 * * 1 cd /path/to/PapersCrawler && python tools/schedule_weekly.py

# 无头服务器需加 xvfb-run（仅每日模式需要，Phase C 需要显示器）
0 2 * * * cd /path/to/PapersCrawler && xvfb-run -a python tools/schedule_daily.py
```

两个调度脚本均尊重 `configs/settings.yaml` 中的 `SKIP_PHASE_*` 配置。
通过 Web UI Config 页面的 SKIP 切换仅影响 Web UI Pipeline 按钮，不影响 CLI 调度脚本。

### 4. 运行测试

**T1/T2 自动化测试（纯离线，零跳过）：**
```bash
pytest tests/ -v                    # 99 个测试全部通过
pytest tests/ -v -k "not pdf"       # 跳过 PDF 测试（需 pandoc 系统依赖）
pytest tests/test_db.py -v          # 单模块
```

**T3 真实集成测试（需配置 .env）：**
```bash
# 一键运行全部真实测试（CrossRef API / DeepSeek API / SMTP 邮件）
bash tests/real/run_all.sh

# 或逐个运行：
python tests/real/real_crossref.py   # CrossRef API 连通性
python tests/real/real_llm_api.py    # DeepSeek API 连通性 + 抓取 fixture
python tests/real/real_email.py      # SMTP 邮件发送测试
```

### 5. 重置流水线状态

所有子命令支持 `--publisher` 过滤，执行前打印影响行数，需输入 `y` 确认。

| 命令 | 重置范围 | 默认条件 | 级联 | 典型用途 |
|------|---------|---------|------|---------|
| `reset-semantic` | `semantic_filter_*`, `semantic_similarity_score`, `semantic_best_subdomain`（5 列） | **全部**（无 status 过滤） | 无 | 修改 sub_domains 后重算语义分 |
| `reset-relevance` | `llm_relevance_*`（6 列） | `failed`/`skipped`（`--all` 含 success） | 无 | 修改 scope_definition 后重判 |
| `reset-publisher` | `publisher_page_fetched_status/error`（2 列） | `failed`/`skipped`（跳过 NonResearchPageError） | 无 | Phase C 被 CF 拦截后重试 |
| `reset-mineru` | `mineru_parse_*`（5 列） | `failed`/`skipped` | 无 | MinerU 超时后重试 |
| `reset-summary` | `llm_summary_*`（4 列） | `failed`/`skipped`（`--all` 含 success） | 无 | 修改 prompt 后重生成总结 |
| `reset-report` | `report_status/date`（2 列） | `reported`（`--today`/`--days` 按日期） | 无 | 重新汇入下次报告 |

**常用示例：**
```bash
# 修改研究领域定义后重新判断所有论文相关性（含已成功的）
python tools/reset_pipeline.py reset-relevance --all

# 仅重置历史判断失败/跳过的论文（修正遗留问题）
python tools/reset_pipeline.py reset-relevance

# 修改 sub_domains 后重算语义相似度分数
python tools/reset_pipeline.py reset-semantic

# Publisher 页面抓取重试
python tools/reset_pipeline.py reset-publisher [--publisher aps]

# MinerU PDF 解析重试
python tools/reset_pipeline.py reset-mineru [--publisher aps]

# LLM 总结重试（仅 failed/skipped）
python tools/reset_pipeline.py reset-summary

# LLM 总结重试（含已成功的）
python tools/reset_pipeline.py reset-summary --all

# 重置所有已报告论文
python tools/reset_pipeline.py reset-report

# 仅重置今天被报告的论文（同一天重试时使用）
python tools/reset_pipeline.py reset-report --today

# 按日历日重置最近 3 天的报告
python tools/reset_pipeline.py reset-report --days 3
```

### 6. 修复 LLM 总结中的 LaTeX 公式格式

LLM 生成的总结有时存在公式分隔符反斜杠丢失（`(\alpha)` 应为 `\(\alpha\)`）或 LaTeX 命令裸写的问题。可使用本工具对已有总结进行修正，无需重跑 Phase F：

```bash
# 预览模式，查看哪些字段需要修复
python tools/fix_summary_formulas.py --dry-run --verbose

# 修复全部已有总结
python tools/fix_summary_formulas.py

# 单篇论文
python tools/fix_summary_formulas.py --doi 10.1103/PhysRevLett.136.123456

# 按出版社过滤
python tools/fix_summary_formulas.py --publisher aps
```

修复逻辑：`FormulaFixer.needs_fix()` 先移除已正确包裹的 `\(...\)` / `\[...\]` 区域，仅当残留 `\command` 时调用 flash 模型。纯文本进/纯文本出，Python 的 `json.dumps()` 自动处理写入 DB 时的 JSON 转义。

### 7. Markdown → PDF 转换

报告默认输出为 Markdown。如需 PDF，提供三种转换方式：

**实验性 — KaTeX 路径（支持 \(\)/\[\] 公式）：**
```bash
python src/processors/md_to_pdf_katex.py data/reports/auto/report_20260607.md
```
使用 marked.js + KaTeX（与 WebUI 报告渲染完全相同）→ cloakbrowser 打印 PDF。公式渲染效果与浏览器一致。

> ⚠️ **实验性功能**：标题间距、分节渲染等细节尚不完善。欢迎反馈改进。

**备用 — pandoc + cloakbrowser：**
```bash
python tools/convert_md_to_pdf.py data/reports/report_20260601.md
```
> ⚠️ 已知问题：`\(`/`\[\]` 公式渲染空白。

### 8. Web UI

提供图形化界面控制流水线、查看状态、管理数据源、生成报告。

> **定位**：Pipeline 监控仪表盘 + 报告工作站，不是 CLI 的替代品。
> **配置隔离**：CLI 使用 `src/config.py`，Web UI 使用独立覆写文件（`data/skip_overrides.json` / `data/journal_overrides.json`），互不干扰。

```bash
# 安装额外依赖
pip install fastapi uvicorn jinja2

# 启动（桌面环境）
PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080

# 启动（无头服务器，Phase C 需要显示）
xvfb-run -a bash -c 'PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080'
```

打开浏览器访问 `http://localhost:8080`。

**页面功能：**
| 页面 | 功能 |
|------|------|
| **Home** | 项目介绍、技术栈标签、架构概览图、Quick Start 三步卡片、出版社/论文统计、快速入门指南 |
| **Pipeline** | 10 阶段（A-RSS / A-CR 独立）Run/Reset 按钮 + 状态柱状图 + SSE 实时日志。Config 页跳过的阶段按钮灰显不可点击 |
| **Papers** | 论文列表，默认按入库日期排序（skipped/pending 置底），可选按发表日期排序。展示语义相似度分（可选）和 LLM 相关性分类（A/B/C/D badge + 图例） |
| **Report** | 勾选有 LLM 总结的论文 → 生成 Markdown 报告 → 浏览器预览 + 下载（写入 `data/reports/user/`） |
| **Data Sources** | 期刊启用/禁用表格，每个期刊可独立控制 RSS 和 CrossRef 数据源。写入 `data/journal_overrides.json` |
| **Logs** | 流水线日志（`data/PaperCrawler.log`），支持按级别过滤 |
| **Subscriptions** | 邮件订阅者管理（添加/删除/启用停用/测试/从 .env 导入），Phase H 优先使用 DB 订阅者列表 |
| **Config** | SKIP 开关切换（影响 Pipeline 页按钮）、研究领域描述编辑、连通性测试（DeepSeek/CrossRef/MinerU）、MinerU Token 过期色标、YAML 编辑器 |

### 9. 调试与辅助工具

```bash
# Markdown → PDF（实验性，KaTeX + cloakbrowser，支持公式）
python src/processors/md_to_pdf_katex.py <input.md> [output.pdf]

# 诊断 LLM Summary JSON 解析失败（打印错误上下文）
python tools/debug_llm_summary.py <doi>

# 用 headful 浏览器诊断 Publisher URL 抓取问题
python tools/debug_publisher_urls.py

# 重置空摘要论文的 Phase D/E/G 状态
python tools/reset_empty_abstract.py
```

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

参见 `src/sources/publisher.py` 中详细注释。核心原则：

1. **Persistent Context** — 同一个 publisher 共用一个浏览器 session
2. **Headful Chromium** — 不使用无头模式（Cloudflare 检测 headless）
3. **cloakbrowser** — 自动处理浏览器指纹伪装，无需手动注入反检测 JS
4. **真人节奏** — 页面间 5~10s 随机延迟，publisher 间冷却 15s
5. **失败熔断** — 同一 publisher 连续 5 篇失败后自动中止
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

- [ ] **热点/趋势分析** — 基于历史论文数据，统计关键词频率变化、新兴研究方向发现
- [ ] **并发升级** — 当前 Phase E/F 使用 ThreadPoolExecutor，但 DB 写入仍是串行瓶颈。考虑异步架构（asyncio + aiosqlite）
- [ ] **无摘要兜底** — Phase E 对无摘要论文标记 skipped，将来可尝试用 OCR/title-only 轻度判断
- [ ] **配置热加载** — 目前配置在 `main()` 入口一次性加载，修改后需重启
