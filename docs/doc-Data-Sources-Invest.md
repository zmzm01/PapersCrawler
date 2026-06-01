# 数据源调研

物理核心期刊：

| 期刊名                                           | 数据来源                                       | ISSN (电子版) |
| ------------------------------------------------ | ---------------------------------------------- | ------------- |
| Nature                                           | CrossRef; RSS; https://dev.springernature.com/ | 1476-4687     |
| Science                                          | CrossRef; RSS                                  | 1095-9203     |
| Physical Review Letters (PRL)                    | CrossRef; RSS                                  | 1079-7114     |
| Physical Review Accelerators and Beams (PRAB)    | CrossRef; RSS                                  | 2469-9888     |
| Physics of Plasmas (POP)                         | CrossRef; RSS                                  | 1089-7674     |
| High Power Laser Science and Engineering (HPLSE) | CrossRef; RSS                                  | 2052-3289     |
| Plasma Physics and Controlled Fusion (PPCF)      | CrossRef; RSS                                  | 1361-6587     |
| Applied Physics Letters (APL)                    | CrossRef; RSS                                  | 1077-3118     |

数据来源：

- RSS
- `CrossRef API`: 经测试，有 DOI, title, author, date, reference, resource ；非 OA 应该拿不到 abstract ！
- `OpenAlex API`: 对于 OA 期刊，应该是可以拿到 Abstract 的，但是对于非 OA 就不行；有些 OA 可以直接获取 PDF 链接地址，有些不行；也提供 ref 关系，但是链接是 OpenAlex 自己的。
  - https://developers.openalex.org/api-reference/introduction
  - https://developers.openalex.org/api-reference/authentication

| OA Status | 含义                                                     |
| --------- | -------------------------------------------------------- |
| `gold`    | 完全开放的期刊文章（正式出版版本），PDF 可公开下载。     |
| `green`   | 作者存档版本在机构仓库或预印本库（可能不是最终出版版）。 |
| `hybrid`  | 期刊本身是订阅制，但作者支付了开放获取费让特定文章 OA。  |
| `closed`  | 非开放访问，需要订阅或购买才能获取。                     |

- `Unpaywall API`: 判断是否 OA 以及获取可能的 OA Location
  - https://unpaywall.org/products/api
- `CORE API`: Real-time machine access to the world's largest corpus of **open access** research papers, containing both metadata and **full texts**.
  - https://core.ac.uk/services/api
- Publisher Crawler
  - 北大校园网环境可以拿到所有文献的访问权限。
  - Playwright 模拟真人绕过 CF Challenge 直接爬取 publisher 页面信息
- ArXiv API

**逐期刊测试**

|         | RSS   | CrossRef | OpenAlex |
| ------- | ----- | -------- | -------- |
| Nature  | True  | True     | True     |
| Science | True  | True     | True     |
| PRL     | True  | True     | True     |
| PRAB    | True  | True     | True     |
| POP     | True  | True     | True     |
| HPLSE   | False | True     | True     |
| APL     | True  | True     | True     |

RSS Links:

- Nature:
  - Nature: https://www.nature.com/nature.rss
  - Nature Physics: https://www.nature.com/nphys.rss
  - Nature Photonics: https://www.nature.com/nphoton.rss
  - Nature Communications: https://www.nature.com/ncomms.rss
- Science:
  - Science (First Release, Latest online): https://www.science.org/action/showFeed?type=axatoc&feed=rss&jc=science
  - Science Advances: https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv
- APS:
  - Physical Review Letters: Editors' suggestions: https://feeds.aps.org/rss/recent/prlsuggestions.xml
  - Physical Review Letters: Plasma and Solar Physics, Accelerators and Beams: https://feeds.aps.org/rss/tocsec/PRL-PlasmaandBeamPhysics.xml
  - Physical Review Accelerators and Beams: Editors' suggestions: https://feeds.aps.org/rss/prstabsuggestions.xml
  - Physical Review Accelerators and Beams: Recently published: https://feeds.aps.org/rss/recent/prstab.xml
  - Physical Review E: Plasma physics: https://feeds.aps.org/rss/tocsec/PRE-Plasmaphysics.xml
  - Physical Review Applied: Editors' suggestions: https://feeds.aps.org/rss/prappliedsuggestions.xml
  - Physical Review Applied: Recently published: https://feeds.aps.org/rss/recent/prapplied.xml
- HPLSE: https://www.cambridge.org/core/rss/product/id/D30FF81AE5FAEE26735889C8553C99DD (似乎**更新不对**)
- IOP:
  - Plasma Physics and Controlled Fusion: https://iopscience.iop.org/journal/rss/0741-3335
- AIP:
  - POP: Current Issue: https://pubs.aip.org/rss/site_1000039/1000022.xml
  - POP: Open Issue: https://pubs.aip.org/rss/site_1000039/LatestOpenIssueArticles_1000022.xml
  - APL: Current Issue: https://pubs.aip.org/rss/site_1000017/1000011.xml
  - APL: Open Issue: https://pubs.aip.org/rss/site_1000017/LatestOpenIssueArticles_1000011.xml
  - Review of Scientific Instruments: Current Issue: https://pubs.aip.org/rss/site_1000041/1000023.xml
  - Review of Scientific Instruments: Open Issue: https://pubs.aip.org/rss/site_1000041/LatestOpenIssueArticles_1000023.xml
- Optica:
  - Optica: https://opg.optica.org/rss/optica_feed.xml
  - Optics Express: https://opg.optica.org/rss/opex_feed.xml
