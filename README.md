# PapersCrawler

> **学术论文自动追踪与推送系统**

自动抓取 7 个出版社 25 个核心期刊的新文章，用 LLM 判相关、用 MinerU 解析 PDF 全文本，
再让 LLM 生成结构化总结，最终通过邮件/静态报告站点推送给研究组。研究领域聚焦
**激光/等离子体/束流物理及束流辐照应用**（加速器方向），可由 `configs/keywords.yaml` 自定义。

```text
RSS / CrossRef → 元数据补全 → 页面爬取 → 标题/摘要初筛
                                              ↓ (A/B/C + low-D)
明确无关终止 ← 正文相关性终审 ← 限额 PDF 解析 → A/B 总结 + C 邻近观察 → 报告 → 邮件
```

## 免责声明

本项目是 **Vibe Coding**（AI 辅助编程）的产物，作者并非专业软件开发者。代码设计、
正确性、安全性及可靠性**不作任何保证**，使用前请自行审查评估。

本项目**不提供绕过期刊付费墙的功能**。论文全文（PDF）的获取依赖于使用者所在机构的
网络订阅。爬虫行为请遵守目标网站的 `robots.txt` 和法律法规。

页面抓取与 Cloudflare 绕过默认使用 [Camoufox](https://camoufox.com/)，
并可在启动或单篇任务失败时自动回退到 cloakbrowser；切换后端前会关闭当前
Playwright 会话，避免同步运行循环冲突。
特此致谢。

## 特性

- **9 阶段流水线**（A-RSS/A-CR → B → C → E → E2 → E3 → F → G → H），SQLite 状态驱动，断点续跑
- **多源元数据**：RSS Feed + CrossRef ISSN 查询，随后用 OpenAlex 按 DOI 补全缺失字段；各来源按非空字段合并
- **人工校准的两阶段 LLM 四级相关性分类**（A/B/C/D）：标题/摘要初筛后对候选做全文终审；可按类别变化触发独立模型复核，当前重点检查高风险 `C → A/B`，并持久化各阶段模型 ID；有效 A/B 进入完整总结，C 以轻量“邻近观察”进入报告，补充严格口径与 prompt 局限可能遗漏的阅读线索
- **可审计的研究范围管理**：`keyword_catalog` 独立维护术语、别名和子域映射，不把单个关键词命中误当成相关性结论；附带覆盖审计和人工标注 benchmark 评分工具
- **25 个期刊覆盖**：APS(9) / AIP(6) / Nature(4) / Science(2) / Optica(2) / Cambridge(1) / IOP(1)
- **来源站点访问策略**：Camoufox 持久化上下文 + 浏览器指纹伪装 + 真人节奏 + Cloakbrowser 独占式自动回退 + 失败熔断；回退失败按单篇隔离，旁路审计不影响抓取；已有 CrossRef/OpenAlex 摘要时跳过页面访问，Bot Manager 阻断自动冷却/隔离；可为 Optica 等来源配置专属访问路由，Phase C 与 E2 共用
- **CLI + WebUI 双模式**：CLI 适合运行/调度，WebUI 提供监控、报告阅览、相关性人工审核、随机待审跳转和独立的旧摘要 D 类比例分层抽查
- **连续审核体验**：人工审核支持整行进入、移动端卡片布局和保存快捷键，详情、返回、分页与随机跳转保留当前筛选上下文
- **统一流水线入口**：日常、每周和全流程运行均通过 `tools/run_pipeline.py`
- **按日分文件日志**：运行日志按日期保存并自动清理旧文件，配套工具可直接统计 WARNING/ERROR；支持用 `PAPERSCRAWLER_LOG_DIR` 隔离测试日志，避免单文件持续膨胀
- **结构化报告输出**：先生成版本化 JSON 快照，再渲染 Markdown；缺失项和 `未提供` 等占位字段不会出现在人读报告或公开站点，自动报告可导出到公开站点
- **统一文本清洗与结构化总结**：解码出版社遗留的 HTML/XML 实体（如 `&#xD;`），修复 LLM JSON 伪转义和公式分隔符，并将 Phase F 总结保存为带稳定 key 和独立局限性字段的 schema v3 JSON；人读报告隐藏内部枚举元数据并采用单层局限条目；公开报告封装为 schema v2
- **可验证公式与印刷级 PDF**：FormulaFixer 先为裸公式添加数学模式包裹，再执行可配置的 KaTeX 校验与 LLM 修复；Markdown 可离线预渲染为静态 KaTeX HTML，再由 Prince 生成 PDF（免费版带水印）
- **多协议 LLM 接入**：按角色支持 Chat Completions、OpenAI Responses 和 Anthropic Messages；可接入 Command Code、OpenCode Zen 等 OpenAI-compatible 网关及其模型，并兼容模型偶发的 Markdown/JSON 格式包装；FormulaFixer 使用独立模型和并发池
- **公开报告导出**：`tools/export_public_reports.py` 将报告 sidecar 导出为静态站点可消费的 JSON
- **历史周报重建**：`tools/rebuild_historical_reports.py` 可跨 `legacy/auto` 按相邻报告日期重建全部历史周报；累计首期仅保留 A/B，其余各期同时收录 C 类邻近观察
- **公开报告站点**：`report-site/` 使用 Astro 静态构建并发布至 Cloudflare Pages，支持下载公开 Markdown；自动报告和公开历史归档可见，组内特别报告保持隔离
- **可检查的静态公式渲染**：Markdown/KaTeX/Prince 脚本带 JSDoc 类型约束，可纳入 Astro 类型检查
- **报告解释页**：`report_YYYYMMDD_explained.html` 展示 LLM prompt 快照
- **逐篇错误隔离**：单篇失败不影响同阶段其他论文
- **ntfy 单条运行汇总**：自动运行结束时以紧凑的 Markdown 展示状态、阶段、相关性、总结和问题；错误示例使用代码块，失败不阻塞流水线

## 快速开始

```bash
# 1) 安装（使用你的 Python 环境）
python -m pip install -r requirements.txt
python -m camoufox fetch

# 2) 配置密钥
cp .env.example .env
# 编辑 .env 填入 CROSSREF_MAILTO / MINERU_TOKEN / OPENROUTER_API_KEY
# llm.active_provider 可在 OpenRouter / Command Code / DeepSeek 间切换

# 3) 自定义研究领域（可选，默认聚焦激光/等离子体/束流）
vim configs/keywords.yaml

# 4) 全流程跑一次
python tools/run_pipeline.py --all                  # 桌面环境
xvfb-run -a python tools/run_pipeline.py --all      # 无头服务器（Phase C 需要 Xvfb）
```

`--all` 会强制执行 A-RSS/A-CR/B/C/E/E2/E3/F/G/H，即使配置中某阶段被 skip；流水线发生阶段错误时 CLI 返回非零退出码，便于 cron 监控。

可选地在 `.env` 配置 ntfy topic/token，并在 `configs/settings.yaml` 开启最终汇总通知。每次自动运行只发送一条面向 ntfy Web App 优化的紧凑 Markdown 汇总，消息标题由 ntfy 的 `title` 展示，正文不重复标题，问题日志放在代码块中；不会发送开始、逐阶段或即时错误通知，也不会添加 Dashboard 或其他公网链接。

启动 Web UI（手动调试）：

```bash
LOG_LEVEL=INFO PYTHONPATH=src uvicorn src.web.app:app --host 127.0.0.1 --port 8080
```

日常运行推荐使用 systemd 管理 WebUI，使其在后台常驻、开机启动并在异常退出后自动重启。
完整配置见 [`deploy/systemd/paperscrawler-web.service`](deploy/systemd/paperscrawler-web.service)
和 [`docs/usage.md`](docs/usage.md#systemd-管理-webui)。打开 http://localhost:8080 查看流水线状态、论文列表、已生成报告，并在“人工审核”页复核正文终审结果或抽查旧摘要筛选。

## 文档

流水线采用“标题+摘要初筛（E）→受持久化配额保护的 PDF/MinerU（E2）→正文相关性终审与高风险类别变化复核（E3）→总结（F）”流程。全文下载默认每日最多 3 篇、单一出版社最多 2 篇，实际下载失败会计入配额；尚未正式出版的 Accepted Paper 只记录状态，不占配额。

研究范围分为自然语言领域定义和可审计的 `keyword_catalog` 两层：前者供 LLM 判断主贡献与语境，后者管理术语覆盖、别名和子域映射。相关性规则允许以核心方向为主体的高价值综述进入 A，并用“具体主贡献、已有定量验证、直接原理映射”三项证据识别 B 类可迁移方法。可用 `tools/keyword_audit.py` 检查配置、`tools/sample_relevance_audit.py` 从旧 D 分层抽样，并用 `tools/evaluate_relevance.py` 评估四分类准确率和 A/B 召回率。

- **[`docs/usage.md`](docs/usage.md)** — 详细使用手册
  （所有入口/工具/配置/工作流/故障排查）
- **[`docs/design.md`](docs/design.md)** — 架构设计与关键决策
- **[`docs/tasks.md`](docs/tasks.md)** — 变更流水账（关键决策与经验教训）
- **`docs/doc-MinerU-Usage.md`** — MinerU API 参考
- **`docs/doc-Data-Sources-Invest.md`** — 数据源调研
- **`docs/doc-DeepSeek-ErrorCodes.md`** — DeepSeek 错误码

## 技术栈

- **语言/框架**：Python 3 + FastAPI（WebUI）
- **数据库**：SQLite（WAL 模式）
- **抓取**：Camoufox（默认）+ Cloakbrowser（自动回退）
- **PDF 解析**：MinerU API
- **LLM**：可切换 Provider 配置集（OpenAI Chat / Responses / Anthropic Messages）
- **配置**：YAML + `.env`（密钥 gitignored）
- **报告站点**：Astro + Node.js/npm；通过项目内 Wrangler 和 `.env` 配置上传到 Cloudflare Pages

## 部署

WebUI 和论文流水线分开管理：WebUI 作为常驻服务交给 systemd，日常/每周流水线继续由
cron 调度。WebUI 不启动浏览器抓取；无头服务器的 `xvfb-run` 只用于包含 Phase C 的流水线。

推荐使用 [`deploy/systemd/paperscrawler-web.service`](deploy/systemd/paperscrawler-web.service)
作为用户级 systemd 模板；具体安装和运维命令见 [`docs/usage.md`](docs/usage.md#systemd-管理-webui)。

典型 cron 部署（`run_daily.sh` + `run_weekly.sh` 包装；两个包装脚本内部统一调用 `tools/run_pipeline.py`）：

```cron
# 每日 Phase A→F（发现 → LLM 总结）
0 2 * * * /path/to/PapersCrawler/run_daily.sh

# 每周日 20:00（Asia/Shanghai）Phase G→H + Cloudflare Pages 部署
0 20 * * 7 /path/to/PapersCrawler/run_weekly.sh
```

包装脚本默认使用 PATH 中的 `python`；conda 或虚拟环境可通过
`PAPERSCRAWLER_PYTHON=/path/to/env/bin/python` 覆盖。

详见 [`docs/usage.md`](docs/usage.md#典型工作流)。

公共仓库保留项目开发历史，但提交使用 GitHub 无回复邮箱；`.env`、运行数据库、报告数据和
机器专属路径不纳入版本控制。

报告站点由周任务自动构建并部署至 Cloudflare Pages。详见
[`docs/usage.md`](docs/usage.md#公开-astro-报告站点)。

## 测试

```bash
pytest tests/ -v                                      # T1/T2 离线测试
pytest tests/ --cov=src --cov-branch --cov-report=term-missing  # 覆盖率
bash tests/real/run_all.sh                            # T3 真实 API 集成测试（需 .env）
```

覆盖率默认统计 `src/`，不触发真实浏览器、LLM、SMTP 或 PDF 服务；`.coveragerc` 当前以
80%（含分支）作为可执行门槛。真实 API 测试会消耗配额，通常只在离线测试通过后运行。

## License

[MIT License](./LICENSE) © 2026 czm.
