# PapersCrawler — 文献自动追踪与推送

自动抓取领域核心期刊文章，筛选与组内工作相关的论文，生成结构化报告并推送。

> **项目不是 Python package** — `src/` 下没有 `__init__.py`，所有 import 相对于项目根目录解析。必须从项目根目录运行。

## 快速开始

### 1. 安装依赖

```bash
pip install requests feedparser beautifulsoup4 parsel pyyaml python-dateutil
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

**configs/keywords.yaml** — 填写研究领域关键词 + 领域段落描述（支持中英文）：

```yaml
domain_description: "(I) Laser-driven ion acceleration..."
keywords:
  - Laser-plasma acceleration
  - Laser wakefield acceleration (LWFA)
  - ...
```

**configs/email.yaml** — 邮件推送配置（可选，不填则跳过）：

```yaml
smtp_host: "smtp.qq.com"
smtp_port: 587
use_tls: true
username: "your_email@qq.com"
password: "your_auth_code"          # 授权码，不是邮箱密码
from_addr: "your_email@qq.com"
to_addrs:
  - "colleague1@example.com"
```

> ⚠️ `.env` 和 `configs/email.yaml` 包含真实密钥，**不要提交到公开仓库**。

配置自检：

```bash
python src/config.py   # 打印已加载的期刊配置
```

### 3. 运行

```bash
# 桌面环境（有显示器）
python src/main.py

# 无图形界面服务器
xvfb-run -a python src/main.py
```

### 4. 运行测试

**T1/T2 自动化测试（纯离线，零跳过）：**
```bash
pytest tests/ -v                    # 83 个测试全部通过
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

```bash
# 语义判断 + 下游重置（更新 domain_description/keywords 后使用）
python tools/reset_pipeline.py reset-semantic [--publisher aps]

# Publisher 抓取重试（仅 failed + skipped）
python tools/reset_pipeline.py reset-publisher [--publisher aps]

# MinerU PDF 解析重试
python tools/reset_pipeline.py reset-mineru [--publisher aps]

# LLM 总结重试
python tools/reset_pipeline.py reset-summary [--publisher aps]

# 重置报告状态，使已报告论文重新出现在下次报告中
python tools/reset_pipeline.py reset-report [--publisher aps]

# 仅重置今天（当前自然日）被报告的论文（同一天重试时使用，避免报告碎片化）
python tools/reset_pipeline.py reset-report --today

# 按日历日重置最近 N 天的报告
python tools/reset_pipeline.py reset-report --days 3
```

所有子命令支持 `--publisher` 过滤，执行前打印 SQL 和影响行数，需输入 `y` 确认。

> **关于报告日期**：`get_papers_for_report()` 以 `report_date IS NULL` 作为过滤条件。论文首次被报告后写入 `report_date`，不再出现在后续报告中。通过 `reset-report --today` 或 `--days N` 可重置指定范围内被报告的论文，适用于当天重试需要合并报告的场景。

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

### 7. Markdown → PDF 转换（实验性）

报告默认输出为 Markdown。如需 PDF，可尝试：

```bash
python tools/convert_md_to_pdf.py data/reports/report_20260601.md
```

> ⚠️ **已知问题**：公式渲染尚不支持，PDF 中公式部分显示为空白。如有公式渲染需求请先使用 Markdown 格式报告。欢迎贡献修复。

### 8. Web UI

提供图形化界面控制流水线、查看状态、生成报告。

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
- **Dashboard** — 各阶段论文状态统计（成功/失败/跳过/待处理）
- **Pipeline** — 点击按钮独立运行每个阶段，实时日志流（SSE）
- **Report** — 选择出版社范围，生成 Markdown 报告
- **Logs** — 流水线日志查看，支持按级别过滤
- **Config** — 只读展示 publishers.yaml / keywords.yaml / 阶段开关状态

### 9. 调试与辅助工具

```bash
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
