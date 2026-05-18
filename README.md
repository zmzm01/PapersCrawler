# PapersCrawler — 文献自动追踪与推送

自动抓取领域核心期刊文章，筛选与组内工作相关的论文，生成结构化报告并推送。

## 项目结构

```
PapersCrawler/
├── configs/
│   ├── publishers.yaml          # 需要追踪的期刊配置 (RSS Feed + 出版社)
│   ├── keywords.yaml            # 研究领域关键词表 (自行填写)
│   ├── email.yaml               # SMTP 邮件推送配置
│   └── prompts/                 # LLM Prompt 模板目录 (预留)
├── data/
│   ├── papers.db                # SQLite 数据库 (自动生成)
│   ├── PaperCrawler.log         # 运行日志
│   ├── raw/
│   │   ├── rss/                 # RSS Feed XML 缓存
│   │   └── page/                # Publisher 页面 HTML 缓存 (调试用)
│   ├── reports/                 # 生成的 Markdown + PDF 报告
│   └── session_cached/          # Playwright 浏览器 Session 缓存
├── docs/                        # 数据源调研与 API 文档
├── tests/                       # 单元测试
│   ├── conftest.py
│   ├── test_db.py               # 数据库操作
│   ├── test_rss.py              # RSS 解析
│   ├── test_crossref.py         # CrossRef 元数据
│   ├── test_publisher_parse.py  # Publisher 页面解析
│   ├── test_relevance.py        # 相关性判断
│   ├── test_report.py           # 报告生成
│   ├── test_pdf.py              # PDF 转换
│   └── test_email.py            # 邮件发送
├── src/
│   ├── config.py                # 全局配置 (路径、API Key、Prompt)
│   ├── main.py                  # 主入口 — 8 阶段流水线
│   ├── sources/
│   │   ├── rss.py               # RSS Feed 抓取与解析
│   │   ├── crossref.py          # CrossRef DOI 元数据查询
│   │   └── publisher.py         # 7 个出版社的页面抓取器
│   ├── utils/
│   │   ├── db.py                # SQLite 数据库 CRUD
│   │   ├── paper_relevance.py   # 关键词匹配 + LLM 相关性判断
│   │   ├── llm_summarize_deepseek.py  # DeepSeek API 论文总结
│   │   ├── paper_report_generator.py  # Markdown / HTML 报告生成
│   │   ├── pdf_converter.py     # Markdown → PDF (pandoc + xelatex)
│   │   └── email_sender.py      # SMTP 邮件发送
│   └── test_for_rss_parse.py    # RSS 解析调试脚本
└── README.md
```

## 流水线架构

整个项目以 SQLite 数据库为中心，按 8 个阶段顺序执行。每个阶段读取上一阶段的输出，处理后写入数据库。

```
Phase A: RSS Feed 抓取
      │  发现论文 → 写入 DOI / 标题 / 链接
      ▼
Phase B: CrossRef 元数据
      │  补充作者 / 出版日期 / 期刊名
      ▼
Phase C: Publisher 页面
      │  爬取摘要 / PDF 链接 (Playwright 浏览器)
      ▼
Phase D: 关键词初筛
      │  统计关键词命中数 → 0 命中则跳过 LLM 判断
      ▼
Phase E: LLM 相关性判断
      │  DeepSeek API → 判定相关/不相关 + 置信度
      ▼
Phase E2: MinerU PDF 全文解析
      │  下载 PDF → MinerU API → 提取 Markdown 全文
      ▼
Phase F: LLM 论文总结
      │  生成结构化总结 (优先用全文, 回退到摘要)
      ▼
Phase G: 报告生成
      │  Markdown + PDF 双格式输出
      ▼
Phase H: 邮件推送
        SMTP 发送报告给团队成员
```

## 快速开始

### 1. 安装依赖

```bash
pip install requests feedparser beautifulsoup4 parsel playwright pyyaml python-dateutil
pip install pytest  # 测试
playwright install chromium  # 安装 Chromium 浏览器
```

### 2. 配置

**configs/keywords.yaml** — 填写你的研究领域关键词：

```yaml
- laser plasma
- wakefield acceleration
- proton acceleration
- inertial confinement fusion
- ultrafast optics
```

**configs/email.yaml** — 填写邮件发送信息（可选，不填则跳过推送）：

```yaml
smtp_host: "smtp.qq.com"
smtp_port: 587
use_tls: true
username: "your_email@qq.com"      # 邮箱账号
password: "your_auth_code"         # 授权码（不是邮箱密码！）
from_addr: "your_email@qq.com"
to_addrs:
  - "colleague1@example.com"
  - "colleague2@example.com"
```

**src/config.py** — 填写 API Key：

```python
CROSSREF_MAILTO = "your_email@example.com"  # CrossRef API 礼貌要求
LLM_API_CONFIG_DICT = {
    "api_key": "sk-your-deepseek-key",      # DeepSeek API Key
    ...
}
```

### 3. 运行

```bash
# 桌面环境
python src/main.py

# 无图形界面服务器 (运行 Publisher 抓取阶段)
xvfb-run -a python src/main.py
```

### 4. 运行测试

```bash
# 运行所有离线测试
pytest tests/ -v

# 跳过 PDF 测试 (需要 pandoc)
pytest tests/ -v -k "not pdf"

# 仅运行数据库测试
pytest tests/test_db.py -v
```

## 支持的出版社/期刊

| 出版社 | 期刊数 | 爬虫类 |
|--------|--------|--------|
| Nature | 4 (Nature, Nature Physics/Photonics/Communications) | `NatureScraper` |
| Science | 2 (Science, Science Advances) | `ScienceScraper` |
| APS | 7 (PRL ×2, PRAB ×2, PRE, PRApplied ×2) | `APSScraper` |
| Cambridge | 1 (HPLSE) | `CambridgeScraper` |
| AIP | 5 (PoP ×2, APL ×2, RSI) | `AIPScraper` |
| IOP | 1 (PPCF) | `IOPScraper` |
| Optica | 2 (Optica, Optics Express) | `OpticaScraper` |

## Publisher 爬虫策略

参见 `src/sources/publisher.py` 中的详细注释。核心原则：

1. **Persistent Context** — 同一个 publisher 共用一个浏览器 session
2. **Headful Chromium** — 不使无头模式（Cloudflare 检测 headless）
3. **固定浏览器指纹** — UA / viewport / locale 固定不变
4. **真人节奏** — 页面间隔 2~30 秒随机延迟
5. **复用 Page** — 不频繁 new_page()
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

- [x] RSS 抓取模块
- [x] CrossRef 元数据抓取模块
- [x] Publisher Scraper 模块
- [x] 关键词筛选相关文献
- [x] LLM 精细判断相关性
- [x] LLM 论文结构化总结
- [x] 报告模板制作 (Markdown + PDF)
- [x] SMTP 分发
- [x] 日志模块
- [x] 分模块测试
- [x] MinerU PDF 解析整合到流水线
- [ ] 语义相似度方法判断相关性 (sentence-transformers)
- [ ] 热点/趋势分析
- [ ] 并发升级 + 数据库同步升级
