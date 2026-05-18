# 项目概述

本项目希望实现抓取领域核心期刊文章，筛选出与组内工作相关的文章，并实现自动推送。

一段时间后可以实现热点与技术进展追踪。

# 项目结构

项目分成 4 个部分，以数据库为中心进行构建。

```
.
├── configs                                           # 配置文件存放处
│   ├── keywords.yaml                                # 本研究领域的关键词表
│   ├── publishers.yaml                              # 需要抓取的 Journal 表
│   └── prompts                                      # 存放 LLM Prompt 处
├── data                                              # 数据目录
│   ├── PaperCrawler.log                             # 运行 log
│   ├── raw                                          # 存放运行过程中的 raw data
│   │   ├── page                                    # 存放部分可能需要保存的 publisher 页面
│   │   └── rss                                     # 存放 rss feed
│   └── reports                                      # 存放生成的报告
├── docs                                              # 存放本项目相关的文档
│   ├── 数据源调研.md
│   └── MinerUAPI文档PDF解析接口文档开发者文档.md
├── README.md                                         # 本项目的说明文档
└── src
    ├── config.py                                     # 存放各种配置
    ├── main.py                                       # 项目主入口
    ├── sources                                       # 数据获取部分
    │   ├── crossref.py                              # crossref metadata 获取
    │   ├── publisher.py                             # publisher page scraper
    │   └── rss.py                                   # rss feed fetch
    ├── test_for_rss_parse.py                         # rss fetch 与解析测试
    └── utils                                         # 各种工具
        ├── db.py                                     # 数据库的创建与管理
        ├── llm_summarize_deepseek.py                 # 用 DeepSeek API 进行 paper 总结
        ├── paper_relevance.py                        # Paper 与本研究领域相关性判断
        └── paper_report_generator.py                 # 报告生成
```

## Part.A 数据抓取

### 多数据源的配置与管理

配置文件 `cofigs/publishers.yaml` 负责配置需要期刊的：

- id (用于方便命名文件)
- 名称
- publish (用于爬虫配置)
- rss feed url
- 其他配置选项

当前配置文件采用列表形式：

```yaml
publishers:
  # Nature Series
  - id: nature
    name: Nature
    publisher: nature
    rss: https://www.nature.com/nature.rss
    enabled: true

  - id: nphys
    name: Nature Physics
    publisher: nature
    rss: https://www.nature.com/nphys.rss
    enabled: true
```

为了读取文件，需要：

```
pip install pyyaml
```

### 数据源优先级与容错策略

```
RSS → DOI
       ↓
Crossref metadata
       ↓
Publisher scrape/API
```

- RSS 负责“发现”
- Crossref 负责“补 metadata”
- Publisher 页面负责“补 non-OA abstract”

### Publisher crawler 策略

已知**直接** `requests` / `https` / `Playwrigt` 会被 cloudflare challenge 阻拦。

对于**校园网环境**，`playwright` + headful chromium + persistent session 可以直接过 CF Challenge 且避开重复 Challenge 。

> **必须使用校园网**，非校园网 IP 质量不清楚，且拿不到全文。
> 服务器可能需要 VPN 接入校园网环境然后 `xvfb + headful chromium` 。

核心原则：伪装成一个真正的科研用户，而不是直接对抗/破解 cloudflare 。

1. 长期复用同一个 Browser
   ```
   启动一次 Chromium
       ↓
   抓几十篇 DOI
       ↓
   最后再关闭
   ```
2. Persistent Context
   ```python
   launch_persistent_context()
   ```
3. 按 publisher 分 session
4. 固定浏览器指纹
   - 不要随机：UA/viewport/locale/timezone
   ```python
   user_agent="固定 Chrome UA"
   locale="zh-CN"
   timezone_id="Asia/Shanghai"
   viewport={"width": 1440, "height": 900}
   ```
5. 不要 headless
6. 加入“真人节奏”

   ```python
   sleep(random.uniform(3, 10))
   ```

   - 偶尔停 20~30 秒
   - 页面间隔不固定

7. 不要每篇 `new_page()` ，复用同一个 page
   ```python
   page.goto(url1)
   page.goto(url2)
   page.goto(url3)
   ```
8. 从“正常入口”进入
   ```python
   page.goto("https://journals.aps.org/")
   page.goto(article)
   ```
9. 降低并发：当前阶段不要多线程
10. 服务器上 `xvfb-run -a python crawler.py`
11. 最关键现实：IP Reputation

| 网络            | 推荐度 |
| --------------- | ------ |
| 学校网络        | 极高   |
| 家宽            | 高     |
| 手机热点        | 中高   |
| VPS             | 低     |
| 香港/新加坡机房 | 更低   |

现阶段可能不需要增强技术：

- playwright stealth plugin
- undetected chromium
- TLS spoof
- JA3 patch

CF 可能的关键检查因素：

| 因素          | 权重 |
| ------------- | ---- |
| IP reputation | 极高 |
| ASN           | 极高 |
| 浏览器真实性  | 高   |
| Headless      | 中   |
| JS challenge  | 低   |

> publisher scraper 应该将 session 数据存放在 `data/browser_cache` 下（不同 publisher 分开）

## Part.B 筛选与解析

提供本研究领域的关键词表，两步筛选：

1. 通过关键词表初筛，如果 match = 0 则直接判断不相关
2. 通过 LLM 判断相关性

## Part.C 报告生成

生成 markdown 报告即可（`paper_report_generator.py` 中写了 html 模板但是其实没什么用），最好转成好看的 PDF （注意 LaTeX 公式转换）。

## Part.D 消息推送

通过 SMTP 发邮件给组里同学：需要邮箱支持 IMAP/SMTP 服务授权（获取授权码）。

# TODOLIST

- [x] RSS 抓取模块
- [x] CrossRef 元数据抓取模块
- [x] Publisher Scraper 模块抓 abstract

- [x] 关键词筛选相关文献
- [x] 对关键词筛选命中的文献，利用 LLM 精细判断相关性。
   - [ ] AI 提供的语义相似度方法判断相关性
- [x] MinerU PDF 解析
- [x] 对于确定相关的文献：生成一句总结、提取关键词和技术点等 LLM 分析。

- [ ] 报告模板制作
- [ ] SMTP 分发 / 下载页面
- [ ] 日志模块
- [ ] 热点/趋势分析（待调研）

进一步优化：

- [ ] RSS 抓取注意请求失败处理？以及 `requests` 基本伪装实现。
- [ ] CrossRef 等多数据源聚合
- [ ] 将4个模块彻底解耦，用数据库作为读写节点。
- [ ] 并发升级（如进行此项需要对数据库进行同步升级！）