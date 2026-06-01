# PapersCrawler — 文献自动追踪与推送

自动抓取领域核心期刊文章，筛选与组内工作相关的论文，生成结构化报告并推送。

> **项目不是 Python package** — `src/` 下没有 `__init__.py`，所有 import 相对于项目根目录解析。必须从项目根目录运行。

## 快速开始

### 1. 安装依赖

```bash
pip install requests feedparser beautifulsoup4 parsel pyyaml python-dateutil
pip install python-dotenv                  # .env 密钥加载
pip install playwright cloakbrowser "cloakbrowser[geoip]"  # 浏览器自动化
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

```bash
pytest tests/ -v                    # 全部离线测试
pytest tests/ -v -k "not pdf"       # 跳过 PDF 测试（需 pandoc）
pytest tests/test_db.py -v          # 单模块
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
```

所有子命令支持 `--publisher` 过滤，执行前打印 SQL 和影响行数，需输入 `y` 确认。

### 6. Markdown → PDF 转换（可选）

报告默认输出为 Markdown。如需 PDF，可手动运行：

```bash
python tools/convert_md_to_pdf.py data/reports/report_20260601.md
```

需系统安装 pandoc + texlive-xelatex：

```bash
sudo apt install pandoc texlive-xetex texlive-latex-extra fonts-noto-cjk
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

- [ ] 热点/趋势分析
- [ ] 并发升级 + 数据库同步升级
