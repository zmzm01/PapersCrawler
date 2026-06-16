# PapersCrawler — 学术论文自动追踪与推送系统

> **免责声明**：本项目是 **Vibe Coding**（AI 辅助编程）的产物，作者并非专业软件开发者。
> 代码设计、正确性、安全性及可靠性**不作任何保证**。使用前请自行审查评估。

> **关于内容获取**：本项目**不提供绕过期刊付费墙的功能**。论文全文（PDF）的获取
> 依赖于使用者所在机构的网络订阅（如校园网、研究所 VPN）——只有机构已购买访问权限的
> 期刊内容才能被正常获取。Publisher 页面抓取的成功率高度依赖于**网络出口 IP 的信誉**
> （校园网通常较优，家庭宽带次之，云服务器/代理通常最差）。爬虫行为请遵守目标网站的
> `robots.txt` 和法律法规。

> 感谢 [cloakbrowser](https://github.com/CloakHQ/cloakbrowser) — 本项目的页面抓取
> 和 Cloudflare 绕过完全依赖这个优秀的开源库。

自动抓取 7 个出版社 21 个期刊的文章 → 语义 + LLM 筛选 → MinerU 全文解析 → LLM 结构化总结 → Markdown 报告 → 邮件推送。

```text
RSS / CrossRef → 元数据补全 → 页面爬取 → 语义排序 → LLM 判相关
    ↓                                          ↓ (A/B 级)
  丢弃不相关                                   PDF 解析 → LLM 总结 → 报告 → 邮件
```

## 快速开始

```bash
# 1. 安装
pip install -r requirements.txt

# 2. 配置密钥
cp .env.example .env
# 编辑 .env: CROSSREF_MAILTO / MINERU_TOKEN / DEEPSEEK_API_KEY

# 3. 运行（桌面环境，全流程 A→H）
python src/main.py

# （无头服务器）
xvfb-run -a python src/main.py
```

浏览器打开 Web UI（推荐日常使用）：
```bash
pip install fastapi uvicorn jinja2
PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080
# 访问 http://localhost:8080
```

## 目录

- [两种运行模式](#两种运行模式) — CLI vs Web UI
- [典型工作流](#典型工作流) — 从零到邮件
- [配置详解](#配置详解)
- [工具索引](#工具索引)
- [Publisher 与爬虫](#publisher-与爬虫)
- [数据流与架构](#数据流与架构)

---

## 两种运行模式

### CLI 模式（适合 cron）

| 命令 | 执行阶段 | 用途 |
|------|---------|------|
| `python src/main.py` | A→H 全流程 | 一次性跑完 |
| `python tools/schedule_daily.py` | A→F（发现→总结） | cron 每日 2:00 |
| `python tools/schedule_weekly.py` | G→H（报告→邮件） | cron 每周一 9:00 |
| `LOG_LEVEL=INFO python tools/schedule_daily.py` | 同上，减少日志 | 调试时用 `DEBUG`，生产用 `INFO` |

所有 CLI 命令读取 `configs/settings.yaml` 的 `skip_phases` 配置，跳过的阶段不执行。

### Web UI 模式（监控仪表盘 + 报告工作站）

```bash
PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080
# 无头服务器：
xvfb-run -a bash -c 'PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080'
```

| 页面 | 功能 |
|------|------|
| **Pipeline** | 逐阶段 Run/Reset + 状态柱状图 + 实时日志。Config 页跳过的阶段按钮灰显 |
| **Papers** | 论文列表（按日期排序），展示 LLM 相关性 A/B/C/D + 子领域标签 |
| **Report** | 勾选论文 → 生成 Markdown 报告 → 预览/下载 |
| **Data Sources** | 逐期刊控制 RSS/CrossRef 开关，独立覆写不影响 publishers.yaml |
| **Subscriptions** | 邮件订阅者管理 + 选择性发送日报 |
| **Config** | SKIP 开关、领域描述编辑、YAML 编辑器、API 连通性测试 |

> **配置隔离**：CLI 只读 `configs/settings.yaml`，Web UI 的 Config 页切换写入 `data/skip_overrides.json`，互不干扰。

---

## 典型工作流

### 从零开始的第一次运行

```bash
# 第 1 步：配置
cp .env.example .env           # 填写 CROSSREF_MAILTO/MINERU_TOKEN/DEEPSEEK_API_KEY
# 编辑 configs/keywords.yaml   # 填写研究领域定义（scope_definition）

# 第 2 步：全流程运行
python src/main.py              # A→H，耗时取决于论文数量

# 第 3 步：查看结果
ls data/reports/auto/           # 日报 Markdown
# 打开 Web UI → Pipeline 页查看各阶段状态
```

### 日常维护（cron + 按需检查）

```cron
# crontab
0 2 * * * cd /path/to/PapersCrawler && xvfb-run -a python tools/schedule_daily.py
0 9 * * 1 cd /path/to/PapersCrawler && python tools/schedule_weekly.py
```

每天早上检查邮件或 Web UI。周一看汇总报告。

### 修改领域定义后重新筛选

```bash
# 修改了 keywords.yaml 的 scope_definition
python tools/reset_pipeline.py reset-relevance --all   # 重新 LLM 判断
python src/main.py                                      # 重跑后续阶段
```

### Phase C 被 Cloudflare 拦截后重试

```bash
python tools/reset_pipeline.py reset-publisher --publisher aps   # 仅重置 APS
python src/main.py                                               # 重跑 Phase C→G
```

### Web UI 中快速生成某几篇论文的报告

1. 打开 **Report** 页
2. 用 Publisher 下拉筛选，勾选需要的论文
3. 点击 **Generate** → 浏览器预览 → 下载 Markdown

### 给团队发送日报

1. **Subscriptions** 页 → 添加成员邮箱
2. 点击 **Send Report** → 勾选收件人 → 确认发送

---

## 配置详解

### `.env` — 密钥（必须）

| 字段 | 说明 |
|------|------|
| `CROSSREF_MAILTO` | 联系邮箱，CrossRef API 要求 |
| `MINERU_TOKEN` | MinerU API Token（解码 JWT 可查过期时间） |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `SMTP_*` | 邮件推送配置（可选，不配则跳过 Phase H） |

### `configs/settings.yaml` — 运行参数

```yaml
skip_phases:                     # 阶段开关
  A_RSS: false                   # true = 跳过
  A_CR: false
  H: true                        # 邮件默认跳过，配好 SMTP 后改为 false
llm:
  relevance: { model: deepseek-v4-flash, thinking: disabled }
  summary:   { model: deepseek-v4-pro, thinking: enabled }
  concurrent_max: 100
pipeline:
  crossref_lookback_days: 1     # A-CR 回溯天数
  max_papers_per_phase: 0       # 0 = 不限制
  skip_nature_news: true
  prefetch_non_research: true   # 浏览器前过滤非论文
publisher:
  page_delay_min: 3             # 页面间隔（秒）
  page_delay_max: 5
  max_consecutive_failures: 3
formula_fix:                    # LLM 总结中 LaTeX 公式修复
  skip: false                   # false = 启用修复
  force: false                  # true = 所有字段强制修复
```

### `configs/keywords.yaml` — 研究领域定义

三个字段决定论文筛选标准：

| 字段 | 用途 | 语种 |
|------|------|------|
| `scope_definition` | Phase E LLM prompt：子领域描述 + 关键词列表 | 中文 |
| `irrelevant_fields` | 不相关领域边界，降低误判 | 中文 |
| `context_gates` | 跨子域消歧规则，如 `fusion` → 直接归 D | 中文 |
| `sub_domains_embedding` | Phase D 语义相似度向量 | 仅英文，<300 词/段 |

`scope_definition` 的子域可独立注释，不关注的域直接 YAML 注释掉。

### `configs/prompts/*.yaml` — LLM 提示词

| 文件 | 用途 |
|------|------|
| `relevance.yaml` | Phase E 相关性判断（英文，含 `{scope_block}` 占位符） |
| `summary.yaml` | Phase F 论文总结（中文，要求 JSON 输出） |
| `fix.yaml` | FormulaFixer LaTeX 修复 |

文件不存在时自动回退到 `config.py` 内嵌后备值。

---

## 工具索引

### 流水线重置

```bash
# 所有 reset 子命令均支持 --publisher 过滤
python tools/reset_pipeline.py <子命令>

reset-semantic     # 重算语义相似度分（Phase D）
reset-relevance    # 重新 LLM 相关性判断（Phase E）
reset-publisher    # 重试 Publisher 页面抓取（Phase C）
reset-mineru       # 重试 MinerU PDF 解析（Phase E2）
reset-summary      # 重新生成 LLM 总结（Phase F）
reset-report       # 重置报告状态（Phase G）
```

### LLM 总结修复

```bash
python tools/fix_summary_formulas.py                     # 修复全部已有总结
python tools/fix_summary_formulas.py --dry-run --verbose  # 预览模式
python tools/fix_summary_formulas.py --doi <doi>          # 单篇
python tools/fix_summary_formulas.py --force              # 强制修复所有字段
```

### 诊断

```bash
python tools/debug_llm_summary.py <doi>          # LLM JSON 解析失败诊断
python tools/debug_publisher_urls.py             # headful 浏览器抓取诊断
python tools/debug_nature_challenge.py           # Nature Client Challenge 诊断
python tools/compare_browsers.py <url>           # 浏览器/HTTP 回退对比
python tools/test_http_fallback.py <url>         # HTTP fallback 连通性测试
python tools/reset_empty_abstract.py             # 重置空摘要论文状态
```

### PDF 转换

```bash
python src/processors/md_to_pdf_katex.py <input.md> [output.pdf]  # KaTeX + cloakbrowser（实验性）
python tools/convert_md_to_pdf.py <input.md>                       # pandoc + cloakbrowser（备用）
```

---

## Publisher 与爬虫

| 出版社 | 期刊数 | 爬虫类 | 反爬策略 |
|--------|--------|--------|---------|
| Nature | 4 | `NatureScraper` | HTTP requests 前置回退（primary） |
| Science | 2 | `ScienceScraper` | `dc.Type` + `og:type` + `altmetric_type` 检测 |
| APS | 7 | `APSScraper` | 同域 PDF 路径扫描 |
| Cambridge | 1 | `CambridgeScraper` | `citation_abstract` meta |
| AIP | 5 | `AIPScraper` | requests+cookie PDF 下载 |
| IOP | 1 | `IOPScraper` | curl_cffi HTTP 回退（fallback） |
| Optica | 2 | `OpticaScraper` | CrossRef 摘要驱动跳过浏览器 |

核心策略：**Persistent Context**（同 publisher 共用浏览器 session）+ **Headful Chromium** + **cloakbrowser** 指纹伪装 + **真人节奏**（3~5s 随机延迟）+ **失败熔断**（连续 3 篇失败后自动中止）。详见 `docs/design.md`。

---

## 数据流与架构

### 8 阶段流水线

```text
Phase A (RSS + CrossRef) ── 发现论文
       ↓
Phase B (CrossRef) ──────── 补充元数据
       ↓
Phase C (Publisher) ─────── 爬取页面 + PDF 链接
       ↓
Phase D (sentence-transformers) ── 语义相似度（仅排序参考）
       ↓
Phase E (DeepSeek) ──────── LLM 判断相关性 → A/B/C/D 四级分类
       ↓
Phase E2 (MinerU) ───────── PDF 全文解析
       ↓
Phase F (DeepSeek) ──────── LLM 结构化总结
       ↓
Phase G ─────────────────── Markdown 报告生成
       ↓
Phase H (SMTP) ──────────── 邮件推送
```

- 数据库 **SQLite** 单表驱动，每阶段三态列（status/error/date），断点续跑
- 逐篇 `try/except` 隔离错误，一篇失败不影响同阶段其他论文
- 完整设计文档：`docs/design.md`（含全部关键决策）
- 变更记录：`docs/tasks.md`

### 文件布局

```
PapersCrawler/
├── configs/              # 配置（YAML）
│   ├── publishers.yaml   #   期刊列表
│   ├── keywords.yaml     #   研究领域定义
│   ├── settings.yaml     #   运行参数
│   └── prompts/          #   LLM 提示词
├── src/                  # 源代码
│   ├── config.py         #   配置加载
│   ├── common.py         #   共享模型 + LLM API 封装
│   ├── db/database.py    #   SQLite CRUD
│   ├── sources/          #   数据源（RSS/CrossRef/Pubisher Scraper）
│   ├── processors/       #   处理器（相关性/总结/报告/邮件）
│   ├── pipeline/         #   流水线编排
│   └── web/              #   Web UI（FastAPI）
├── tools/                # 辅助工具
│   ├── schedule_daily.py #   每日 cron
│   ├── schedule_weekly.py#   每周 cron
│   ├── reset_pipeline.py #   状态重置
│   └── fix_summary_formulas.py
├── templates/email/      # 邮件 HTML 模板
├── data/                 # 运行时数据（gitignored）
│   ├── reports/auto/     # 自动日报
│   ├── reports/user/     # 用户自选报告
│   └── models/           # sentence-transformers 本地模型
└── docs/                 # 文档
    ├── design.md         #   架构设计
    └── tasks.md          #   变更记录
```

### 测试

```bash
pytest tests/ -v                   # T1/T2 离线测试（零跳过）
bash tests/real/run_all.sh         # T3 真实 API 集成测试（需 .env）
```

---

## MIT License

```
MIT License

Copyright (c) 2026 czm

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
