"""
paper_report_generator.py (v2)
===============================
根据论文信息字典自动生成 Markdown / HTML 报告。

核心功能：
- 接收单篇或多篇论文的结构化信息（标题、作者、日期、DOI、URL 以及 LLM 生成的总结字段）。
- 自动生成格式化的 Markdown 或 HTML 报告，支持目录（TOC）生成。
- 处理 main_results_and_physics 字段中的 Markdown 标题，自动将其重定级（re-level）以适应报告整体结构。

模块组成概览：

【辅助函数（private helpers）】
- _fix_latex_backslashes: 将双反斜杠还原为单反斜杠，修复 LLM 输出中 LaTeX 命令的转义问题。
- _process_text_for_markdown: 处理普通文本字段，修复 LaTeX 并将 \n 转为 Markdown 强制换行（行尾两个空格 + 换行）。
- _process_text_for_html: 处理普通文本字段用于 HTML 输出（修复 LaTeX → HTML 转义 → \n 替换为 <br>）。
- _adjust_headings: 标题重定级算法——将 Markdown 文本中的内部标题上移/下移若干级别。
- _process_results_markdown: 综合处理 main_results_and_physics 字段（修复 LaTeX + 标题重定级 + 换行转换）。
- _authors_str: 将作者列表（List[str]）转换为逗号分隔的字符串。
- _make_markdown_section: 为单篇论文生成 Markdown 片段（## 标题 + 元信息 + 结构化总结内容）。
- _make_html_section: 为单篇论文生成 HTML 片段（<section> + 元信息 + 结构化总结内容）。

【公共接口（public API）】
- generate_markdown: 生成 Markdown 格式报告（支持多篇论文、目录、可配置的标题起始级别）。
- generate_html: 生成 HTML 格式报告（支持完整文档模式或纯 body 模式）。
- generate_report: 统一报告生成接口，根据 format 参数路由到 markdown 或 html 生成函数。
"""

from typing import Dict, List, Union, Optional
import re


def _fix_latex_backslashes(text: str) -> str:
    """
    将双反斜杠 \\\\ 替换为单反斜杠 \\，恢复 LaTeX 命令。

    为什么需要这个函数：
    DeepSeek API 的 JSON Output 模式下，LaTeX 命令中的反斜杠（如 \omega, \frac）会被 JSON 序列化
    转义为双反斜杠（\\omega, \\frac）。这是因为 JSON 规范要求字符串中的反斜杠用 \\ 表示。
    在生成可读报告时，需要将这些双反斜杠还原为正常的 LaTeX 语法。

    示例：
    - 输入: "电子能量 \\\\(E = \\\\gamma m c^2\\\\)"  →  输出: "电子能量 \\(E = \\gamma m c^2\\)"
    - 输入: "\\\\(\\\\omega\\\\) 表示激光频率"  →  输出: "\\(\\omega\\) 表示激光频率"
    """
    return text.replace('\\\\', '\\')


def _process_text_for_markdown(text: str) -> str:
    """
    处理普通字段用于 Markdown 输出：

    1. 修复 LaTeX 反斜杠（_fix_latex_backslashes）
    2. 将 \\n 转换为 Markdown 强制换行：
       Markdown 中，行尾的两个空格后跟换行符表示强制换行（hard line break，类似 <br>）。
       这样 LLM 输出的多行文本在 Markdown 渲染后仍能保持原有的段落和分行结构。

    示例：
    - 输入: "第一行\\n第二行\\n第三行"  →  输出: "第一行  \\n第二行  \\n第三行"
    （注意：每行末尾增加了两个空格，配合换行符形成 Markdown hard break）
    """
    text = _fix_latex_backslashes(text)
    lines = text.split('\n')
    return '  \n'.join(lines)


def _adjust_headings(markdown_text: str, base_level: int = 4) -> str:
    """
    调整 Markdown 文本中的 ATX 标题（# 开头）级别，使最高级标题从 base_level 开始。

    【算法说明——标题重定级（Heading Re-leveling）】

    问题背景：
    LLM 在生成 main_results_and_physics 字段时，可能使用 # 一级标题组织内容。
    但在报告整体结构中，论文标题本身已用 ## 二级标题，论文内部子标题应在此基础上进一步缩进。
    例如：
      ## 论文标题（2 级）
      ### 研究动机（3 级）
      ### 主要结果（3 级）
          # 结果1           ← 这里的 # 是 LLM 输出的，级别太高，会破坏文档层次
          # 结果2           ← 同上

    期望效果：
      ## 论文标题（2 级）
      ### 研究动机（3 级）
      ### 主要结果（3 级）
          #### 结果1       ← 自动降为 4 级标题
          #### 结果2       ← 同上

    算法步骤：
    1. 正则匹配所有 ATX 风格标题行（行首 1~6 个 # 后跟空格和内容）。
    2. 如果没有标题 → 返回原文本（无需处理）。
    3. 找到文本中最高级别的标题（即 # 数量最少的那个，min_level）。
    4. 计算偏移量: shift = base_level - min_level。
       - 如果 shift > 0：标题需要"下移"（增加 # 数量），例如 min_level=1, base_level=4 → 所有标题加 3 个 #。
       - 如果 shift <= 0：文本中已有标题级别已经 >= base_level，无需调整。
    5. 对每个标题应用偏移，同时保证不超过 Markdown 的 6 级标题上限。

    示例：
    - 输入文本: "# 结果\n## 细节"    base_level=4
    - 检测到 min_level=1，shift=3
    - 输出: "#### 结果\n##### 细节"

    边界情况：
    - 偏移后标题超过 6 级 → 截断为 6 级（Markdown 规范最多 6 级）。
    - 文本中没有标题 → 原样返回。
    - 文本中最低级别已经是 3，base_level=4 → shift=1，仅下移 1 级。

    Parameters
    ----------
    markdown_text : str
        包含 Markdown 标题的文本（通常来自 LLM 输出的 main_results_and_physics 字段）。
    base_level : int
        期望的最高标题级别（即文本中最高标题应调整到的级别），默认为 4。

    Returns
    -------
    str
        标题级别调整后的 Markdown 文本。
    """
    # 匹配行首的 # 序列（ATX 风格标题）
    # 正则说明：(#{1,6}) 捕获 1~6 个 #，(.*) 捕获标题内容
    heading_pattern = re.compile(r'^(#{1,6})\s+(.*)', re.MULTILINE)
    matches = heading_pattern.findall(markdown_text)
    if not matches:
        return markdown_text  # 无标题，无需调整

    # 找到当前文本中最高的标题级别（# 最少的个数）
    levels = [len(h[0]) for h in matches]
    min_level = min(levels)
    shift = base_level - min_level

    # 如果已经比 base_level 深，或偏移为负，则不调整（避免标题变浅）
    # 例如：文本中最低标题已是 4 级，base_level=3 → shift=-1，不应将标题提升级别
    if shift <= 0:
        return markdown_text

    def replacer(match):
        hashes = match.group(1)   # 匹配到的 # 序列
        content = match.group(2)  # 标题文本内容
        new_hashes = '#' * (len(hashes) + shift)
        # 保证不超过 6 级（Markdown 规范上限）
        if len(new_hashes) > 6:
            new_hashes = '#' * 6
        return f'{new_hashes} {content}'

    # 使用 re.sub 替换所有匹配到的标题行
    return heading_pattern.sub(replacer, markdown_text)


def _process_results_markdown(text: str, base_heading_level: int = 4) -> str:
    """
    专门处理 main_results_and_physics 字段：

    处理步骤（按顺序）：
    1. _fix_latex_backslashes: 修复 LLM JSON 输出中的双反斜杠
    2. _adjust_headings: 调整内部标题层级，使其适配报告的主体结构
    3. 将 \\n 转换为 Markdown 强制换行（行尾两个空格 + 换行符）

    为什么这个字段需要特殊处理？
    - main_results_and_physics 是唯一一个内部可能包含 Markdown 标题的字段。
    - 其他字段（如 motivation_and_goal、key_setup_and_method）通常没有标题，只需基本的转义处理。
    - 通过 _adjust_headings 重新定位标题级别，确保内部标题不会破坏文档的整体层次结构。

    Parameters
    ----------
    text : str
        main_results_and_physics 的原始文本（来自 LLM JSON 输出）
    base_heading_level : int
        内部标题的起始级别，默认为 4（对应 #### 标题）

    Returns
    -------
    str
        处理后的 Markdown 文本
    """
    text = _fix_latex_backslashes(text)
    text = _adjust_headings(text, base_level=base_heading_level)
    lines = text.split('\n')
    text = '  \n'.join(lines)
    return text


def _process_text_for_html(text: str) -> str:
    """
    处理文本用于 HTML 输出：

    处理步骤：
    1. _fix_latex_backslashes: 修复双反斜杠
    2. html.escape: 转义 HTML 特殊字符（<, >, &, " 等），防止 XSS 和渲染错误
    3. 将 \\n 替换为 <br>\\n，在 HTML 中实现换行

    注意：HTML 模式下不进行标题重定级。HTML 使用 h1~h6 标签，
    如果 LLM 输出中包含 Markdown 标题，将不会被转换为 HTML 标题标签。
    如需 HTML 格式的标题层次，建议使用 Markdown → HTML 转换器（如 markdown 库）。
    """
    import html
    text = _fix_latex_backslashes(text)
    text = html.escape(text)     # HTML 实体转义，防止注入
    text = text.replace('\n', '<br>\n')
    return text


def _authors_str(authors: List[str]) -> str:
    """
    将作者列表转换为逗号分隔的字符串。

    示例：
    - ["张三", "李四", "王五"] → "张三, 李四, 王五"
    - [] → ""
    """
    return ', '.join(authors)


# ======================================================================
# Markdown 生成
# ======================================================================

def _make_markdown_section(paper: Dict, heading_base: int = 4) -> str:
    """
    为单篇论文生成 Markdown 片段。

    生成的结构（按顺序）：
    ## {标题}                     ← 固定使用 ## 二级标题（每篇论文的顶级标题）
    **作者**: ...
    **日期**: ...
    **DOI**: ...（可选）
    **页面**: ...（可选）
    **PDF**: ...（可选）
    **一句话**: ...
    ### 研究动机与目标             ← 使用 ### 三级标题
    {motivation_and_goal 内容}
    ### 关键方法与设置
    {key_setup_and_method 内容}
    ### 主要结果与物理内涵
    {main_results_and_physics 内容}  ← 内部标题已通过 _adjust_headings 重定级
    ### 要点总结
    {take_home_message 内容}
    ---                           ← 分割线，分隔不同论文

    层次设计：
    - 每篇论文的顶级标题 = ## （2 级）
    - 论文内部子标题 = ### （3 级）：研究动机、关键方法、主要结果、要点总结
    - 主要结果内部标题 = 由 heading_base 参数控制（默认 4 级，即 ####）

    Parameters
    ----------
    paper : Dict
        论文信息字典，包含 title, authors, date, doi, page_url, pdf_url 等元信息字段，
        以及 one_sentence, motivation_and_goal, key_setup_and_method,
        main_results_and_physics, take_home_message 等 LLM 总结字段。
    heading_base : int
        main_results_and_physics 内部标题的起始级别，默认为 4。

    Returns
    -------
    str
        单篇论文的 Markdown 片段。
    """
    title = paper.get('title', '无标题')
    authors = _authors_str(paper.get('authors', []))
    date = paper.get('date', '未知')
    doi = paper.get('doi', '')
    page_url = paper.get('page_url', '')
    pdf_url = paper.get('pdf_url', '')
    abstract = _process_text_for_markdown(paper.get('abstract', ''))
    # 各字段分别处理：普通字段用 _process_text_for_markdown，结果字段用 _process_results_markdown
    one_sentence = _process_text_for_markdown(paper.get('one_sentence', ''))
    motivation = _process_text_for_markdown(paper.get('motivation_and_goal', ''))
    method = _process_text_for_markdown(paper.get('key_setup_and_method', ''))
    results = _process_results_markdown(paper.get('main_results_and_physics', ''), heading_base)
    take_home = _process_text_for_markdown(paper.get('take_home_message', ''))

    md = f"## {title}\n\n"
    md += f"**作者**: {authors}  \n"
    md += f"**日期**: {date}  \n"
    if doi:
        md += f"**DOI**: [{doi}](https://doi.org/{doi})  \n"
    if page_url:
        md += f"**页面**: [链接]({page_url})  \n"
    if pdf_url:
        md += f"**PDF**: [下载]({pdf_url})  \n"
    md += "\n"
    if abstract:
        md += f"**原文摘要**: {abstract}\n\n"
    md += f"**一句话**: {one_sentence}\n\n"
    md += f"### 研究动机与目标\n\n{motivation}\n\n"
    md += f"### 关键方法与设置\n\n{method}\n\n"
    md += f"### 主要结果与物理内涵\n\n{results}\n\n"
    md += f"### 要点总结\n\n{take_home}\n\n"
    md += "---\n\n"
    return md


def generate_markdown(papers: Union[Dict, List[Dict]], toc: bool = False,
                      results_heading_base: int = 4) -> str:
    """
    生成 Markdown 格式的报告。

    生成逻辑：
    1. 如果 papers 是单篇字典，包装为列表统一处理。
    2. 多篇时生成 # 一级标题"文献报告"和可选的目录（TOC）。
       - TOC 通过 Markdown 链接 + 锚点（anchor）实现，锚点为标题或将空格替换为 - 后得到（会损失中文支持）。
    3. 遍历每篇论文，调用 _make_markdown_section 生成片段并拼接。

    Args:
        papers: 单篇论文字典或列表。
        toc: 是否生成目录（仅在 papers 为多篇列表时生效）。
        results_heading_base: main_results_and_physics 内部标题的起始级别，默认为 4（####）。

    Returns:
        生成的 Markdown 报告字符串。
    """
    if isinstance(papers, dict):
        papers = [papers]

    doc = ""
    if len(papers) > 1:
        doc += "# 文献报告\n\n"
        if toc:
            doc += "## 目录\n\n"
            for i, p in enumerate(papers, start=1):
                title = p.get('title', f'论文{i}')
                # 简单生成锚点，替换空格
                # 注意：这种方式对中文标题不完美，但 Markdown 渲染器通常能处理
                anchor = title.replace(' ', '-')
                doc += f"- [{i}. {title}](#{anchor})\n"
            doc += "\n---\n\n"

    for p in papers:
        doc += _make_markdown_section(p, heading_base=results_heading_base)

    return doc


# ======================================================================
# HTML 生成
# ======================================================================

def _make_html_section(paper: Dict) -> str:
    """
    为单篇论文生成 HTML 片段。

    生成的结构：
    <section>
      <h2>{标题}</h2>                     ← 固定 h2 二级标题
      <p><strong>作者:</strong> ...</p>   ← 元信息
      <p><strong>一句话:</strong> ...</p>
      <h3>研究动机与目标</h3>             ← 使用 h3 三级标题
      <p>...</p>
      <h3>关键方法与设置</h3>
      <p>...</p>
      <h3>主要结果与物理内涵</h3>
      <p>...</p>
      <h3>要点总结</h3>
      <p>...</p>
    </section>
    <hr>

    字段处理：
    - 普通文本字段经过 _process_text_for_html 处理（修复 LaTeX + HTML 转义 + \n→<br>）。
    - 注意：HTML 模式下不对 Markdown 标题做重定级处理，因为 Markdown 标记在 HTML 中不被渲染。
      如需 HTML 中的标题层次，应使用 Markdown → HTML 转换器。
    """
    title = _process_text_for_html(paper.get('title', '无标题'))
    authors = _authors_str(paper.get('authors', []))
    date = paper.get('date', '未知')
    doi = paper.get('doi', '')
    page_url = paper.get('page_url', '')
    pdf_url = paper.get('pdf_url', '')
    abstract = _process_text_for_html(paper.get('abstract', ''))
    one_sentence = _process_text_for_html(paper.get('one_sentence', ''))
    motivation = _process_text_for_html(paper.get('motivation_and_goal', ''))
    method = _process_text_for_html(paper.get('key_setup_and_method', ''))
    results = _process_text_for_html(paper.get('main_results_and_physics', ''))
    take_home = _process_text_for_html(paper.get('take_home_message', ''))

    html = f"<section>\n  <h2>{title}</h2>\n"
    html += f"  <p><strong>作者:</strong> {authors}<br>\n"
    html += f"  <strong>日期:</strong> {date}<br>\n"
    if doi:
        html += f"  <strong>DOI:</strong> <a href=\"https://doi.org/{doi}\">{doi}</a><br>\n"
    if page_url:
        html += f"  <strong>页面:</strong> <a href=\"{page_url}\">{page_url}</a><br>\n"
    if pdf_url:
        html += f"  <strong>PDF:</strong> <a href=\"{pdf_url}\">{pdf_url}</a></p>\n"
    if abstract:
        html += f"  <p><strong>原文摘要:</strong> {abstract}</p>\n"
    html += f"  <p><strong>一句话:</strong> {one_sentence}</p>\n"
    html += f"  <h3>研究动机与目标</h3>\n  <p>{motivation}</p>\n"
    html += f"  <h3>关键方法与设置</h3>\n  <p>{method}</p>\n"
    html += f"  <h3>主要结果与物理内涵</h3>\n  <p>{results}</p>\n"
    html += f"  <h3>要点总结</h3>\n  <p>{take_home}</p>\n"
    html += "</section>\n<hr>\n"
    return html


def generate_html(papers: Union[Dict, List[Dict]], full_document: bool = True) -> str:
    """
    生成 HTML 格式的报告。

    生成逻辑：
    1. 如果 papers 是单篇字典，包装为列表。
    2. 遍历每篇论文，调用 _make_html_section 生成 <section> 片段并拼接为 body。
    3. 如果 full_document=True，将 body 嵌入完整的 HTML5 文档模板（含内联 CSS 样式）。
       否则只返回 body 内容（适合嵌入到已有页面中）。

    内联 CSS 样式说明：
    - 使用系统字体栈（Segoe UI, system-ui），在 Windows/macOS/Linux 上都有良好的渲染。
    - 最大宽度 900px，居中显示，适合桌面阅读。
    - section 卡片风格：白色背景、圆角、浅阴影，视觉上与论文元信息区分。
    - 配色：标题用深蓝灰色（#2c3e50），链接用浅蓝色（#3498db）。

    Args:
        papers: 单篇论文字典或列表。
        full_document: 是否返回完整的 HTML 文档（含 <!DOCTYPE>, <head>, CSS 样式）。
                       设为 False 时仅返回 body 内部内容，适合嵌入已有页面。

    Returns:
        生成的 HTML 字符串。
    """
    if isinstance(papers, dict):
        papers = [papers]

    body = ""
    for p in papers:
        body += _make_html_section(p)

    if not full_document:
        return body

    # 完整 HTML 文档模板，包含响应式设计和面向中文阅读优化的排版
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>文献报告</title>
  <style>
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      line-height: 1.6;
      max-width: 900px;
      margin: 40px auto;
      padding: 0 20px;
      color: #333;
      background: #fafafa;
    }}
    h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
    h2 {{ color: #2c3e50; }}
    h3 {{ color: #34495e; }}
    section {{
      background: white;
      padding: 20px 25px;
      margin: 30px 0;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }}
    hr {{
      border: none;
      height: 1px;
      background: #ddd;
      margin: 40px 0;
    }}
    a {{ color: #3498db; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    p {{ margin: 0.5em 0; }}
    strong {{ color: #555; }}
  </style>
</head>
<body>
  <h1>文献报告</h1>
{body}
</body>
</html>"""
    return html


# ======================================================================
# 统一报告生成接口
# ======================================================================

def generate_report(papers: Union[Dict, List[Dict]], format: str = 'markdown',
                    toc: bool = False, full_html: bool = True,
                    results_heading_base: int = 4) -> str:
    """
    统一的报告生成接口。

    根据 format 参数自动路由到 Markdown 或 HTML 生成函数。

    Args:
        papers: 单篇论文字典或列表。字典需包含 title, authors, one_sentence 等字段。
        format: 输出格式，支持 'markdown', 'md', 'html'。
        toc: 仅 Markdown 格式生效。是否在多篇论文时生成目录。
        full_html: 仅 HTML 格式生效。是否返回完整 HTML 文档（含 CSS 样式和 head 元信息）。
        results_heading_base: 仅 Markdown 格式生效。main_results_and_physics 内部标题的起始级别，默认为 4。

    Returns:
        生成的报告字符串。

    Raises:
        ValueError: 当 format 参数不是 'markdown', 'md', 'html' 之一时抛出。
    """
    fmt = format.lower()
    if fmt in ('markdown', 'md'):
        return generate_markdown(papers, toc=toc, results_heading_base=results_heading_base)
    elif fmt == 'html':
        return generate_html(papers, full_document=full_html)
    else:
        raise ValueError(f"不支持的格式: {format}，可选 'markdown' 或 'html'")


# ===== 使用示例 =====
if __name__ == '__main__':
    paper_example = {
        "title": "用超快光谱探测二维材料中的激子凝聚",
        "authors": ["张三", "李四", "王五"],
        "date": "2025-04-15",
        "doi": "10.1234/example.2025.001",
        "page_url": "https://journal.example.com/article/001",
        "pdf_url": "https://journal.example.com/article/001/pdf",
        "one_sentence": "本文采用时间分辨角分辨光电子能谱（trARPES），研究了单层WSe₂中激子凝聚的动力学过程，得到了凝聚体形成时间约为 200\\,fs 的核心结论。",
        "motivation_and_goal": "激子凝聚是否在室温下存在仍存争议。\\citet{ref1} 报道了稳态信号，但缺少超快动力学证据。本文目标：直接观测凝聚形成与退相干的时间尺度。",
        "key_setup_and_method": "使用 800\\,nm 泵浦、极紫外探测的 trARPES 系统，时间分辨率 50\\,fs。样品为 hBN 封装的单层 WSe₂，温度 80\\,K。核心公式：\\Delta n(k,t) \\propto |\\psi(k,t)|^2。",
        # 注意：内部包含 Markdown 标题 # 和 ##——在生成报告时会通过 _adjust_headings 自动重定级
        "main_results_and_physics": "# 凝聚形成时间\n泵浦后 180~220\\,fs 建立，指数上升 $\\tau_r = 60\\pm 10$\\,fs。\n\n# 动量分布窄化\nFWHM 从 0.3\\,Å⁻¹ 缩小到 0.1\\,Å⁻¹，符合宏观相干态。\n\n# 退相干机制\n退相干时间约 1.2\\,ps，归因于激子-声子散射。\n\n# 阈值密度\n临界密度 $n_c \\approx 1.2\\times 10^{12}$ cm⁻²，与 BKT 相变一致。",
        "take_home_message": "首次用超快 trARPES 直接观测到激子凝聚的时间动力学，为室温激子器件提供了关键参数。局限在于未能定量分离缺陷对退相干的影响。"
    }

    # 生成 Markdown（自动将 # 标题降为 #### 标题）
    # _adjust_headings 检测到内部 min_level=1, base_level=4 → shift=3 → # → ####
    md = generate_report(paper_example, format='markdown', results_heading_base=4)
    print("=== Markdown (标题自动降级) ===")
    print(md)

    # 也可以改为从 3 级开始
    # _adjust_headings 检测到内部 min_level=1, base_level=3 → shift=2 → # → ###
    md2 = generate_report(paper_example, format='markdown', results_heading_base=3)
    print("\n=== Markdown (标题从 ### 开始) ===")
    print(md2)
