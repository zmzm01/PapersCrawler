# PapersCrawler

> **学术论文自动追踪与推送系统**

自动抓取 7 个出版社 25 个核心期刊的新文章，用 LLM 判相关、用 MinerU 解析 PDF 全文本，
再让 LLM 生成结构化总结，最终通过邮件/Hugo 站点推送给研究组。研究领域聚焦
**激光/等离子体/束流物理**（加速器方向），可由 `configs/keywords.yaml` 自定义。

```text
RSS / CrossRef → 元数据补全 → 页面爬取 → 标题/摘要初筛
                                              ↓ (A/B/C + low-D)
明确无关终止 ← 正文相关性终审 ← 限额 PDF 解析 → A/B 总结 → 报告 → 邮件
```

## 免责声明

本项目是 **Vibe Coding**（AI 辅助编程）的产物，作者并非专业软件开发者。代码设计、
正确性、安全性及可靠性**不作任何保证**，使用前请自行审查评估。

本项目**不提供绕过期刊付费墙的功能**。论文全文（PDF）的获取依赖于使用者所在机构的
网络订阅。爬虫行为请遵守目标网站的 `robots.txt` 和法律法规。

页面抓取与 Cloudflare 绕过完全依赖 [cloakbrowser](https://github.com/CloakHQ/cloakbrowser)，
特此致谢。

## 特性

- **9 阶段流水线**（A-RSS/A-CR → B → C → E → E2 → E3 → F → G → H），SQLite 状态驱动，断点续跑
- **双源发现**：RSS Feed + CrossRef ISSN 查询，智能回溯补漏
- **两阶段 LLM 四级相关性分类**（A/B/C/D）：初筛 A/B/C + 低置信 D 进入限额正文终审，终审 A/B 才进入总结与报告
- **25 个期刊覆盖**：APS(9) / AIP(6) / Nature(4) / Science(2) / Optica(2) / Cambridge(1) / IOP(1)
- **Publisher 爬虫**：cloakbrowser 持久化上下文 + 浏览器指纹伪装 + 真人节奏 + 失败熔断
- **CLI + WebUI 双模式**：CLI 适合运行/调度，WebUI 提供只读监控与报告阅览
- **报告双输出**：自动日报（邮件）+ 可由 CLI 工具生成的预览报告
- **报告解释页**：`report_<date>_explained.html` 展示 LLM prompt 快照
- **逐篇错误隔离**：单篇失败不影响同阶段其他论文

## 快速开始

```bash
# 1) 安装（使用你的 Python 环境）
python -m pip install -r requirements.txt

# 2) 配置密钥
cp .env.example .env
# 编辑 .env 填入 CROSSREF_MAILTO / MINERU_TOKEN / DEEPSEEK_API_KEY

# 3) 自定义研究领域（可选，默认聚焦激光/等离子体/束流）
vim configs/keywords.yaml

# 4) 全流程跑一次
python tools/run_pipeline.py --all                  # 桌面环境
xvfb-run -a python tools/run_pipeline.py --all      # 无头服务器（Phase C 需要 Xvfb）
```

启动 Web UI（推荐日常使用）：

```bash
PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080
# 无头服务器：xvfb-run -a bash -c 'PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080'
```

打开 http://localhost:8080 查看 Pipeline 状态、Papers 列表和已生成报告。

## 文档

流水线采用“标题+摘要初筛（E）→受持久化配额保护的 PDF/MinerU（E2）→正文相关性终审（E3）→总结（F）”流程。全文下载默认每日最多 3 篇、单一出版社最多 2 篇，失败尝试同样计入配额。

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
- **抓取**：cloakbrowser（Persistent Context 绕过 Cloudflare）
- **PDF 解析**：MinerU API
- **LLM**：OpenAI 兼容 API（默认 DeepSeek；可在 `llm.base_url` 切换网关）
- **配置**：YAML + `.env`（密钥 gitignored）

## 部署

典型 cron 部署（`run_daily.sh` + `run_weekly.sh` 包装）：

```cron
# 每日 Phase A→F（发现 → LLM 总结）
0 10 * * * /path/to/PapersCrawler/run_daily.sh

# 每周日 20:00（Asia/Shanghai）Phase G→H + Hugo 部署
0 20 * * 7 /path/to/PapersCrawler/run_weekly.sh
```

详见 [`docs/usage.md`](docs/usage.md#典型工作流)。

## 测试

```bash
pytest tests/ -v                  # T1/T2 离线测试
bash tests/real/run_all.sh        # T3 真实 API 集成测试（需 .env）
```

## License

[MIT License](./LICENSE) © 2026 czm.
