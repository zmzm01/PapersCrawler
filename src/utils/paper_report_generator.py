"""
paper_report_generator.py (v2)
根据论文信息字典自动生成 Markdown / HTML 报告。
支持处理 main_results_and_physics 内部的多级标题，自动适配到合适的层级。
"""

from typing import Dict, List, Union, Optional
import re


def _fix_latex_backslashes(text: str) -> str:
    """将双反斜杠 \\ 替换为单反斜杠 \，恢复 LaTeX 命令。"""
    return text.replace('\\\\', '\\')


def _process_text_for_markdown(text: str) -> str:
    """
    处理普通字段用于 Markdown 输出：
    - 修复 LaTeX 反斜杠
    - 将 \n 转换为行尾两个空格 + 换行（Markdown 强制换行）
    """
    text = _fix_latex_backslashes(text)
    lines = text.split('\n')
    return '  \n'.join(lines)


def _adjust_headings(markdown_text: str, base_level: int = 4) -> str:
    """
    调整 Markdown 文本中的 ATX 标题（# 开头）级别，使最高级标题从 base_level 开始。
    例如 base_level=4 时，内部的 '# 标题' 变为 '#### 标题'，'## 标题' 变为 '##### 标题'。

    如果文本中没有标题，或偏移量不可能非负，则原样返回。
    """
    # 匹配行首的 # 序列（ATX 风格标题）
    heading_pattern = re.compile(r'^(#{1,6})\s+(.*)', re.MULTILINE)
    matches = heading_pattern.findall(markdown_text)
    if not matches:
        return markdown_text

    # 找到当前文本中最高的标题级别（# 最少的个数）
    levels = [len(h[0]) for h in matches]
    min_level = min(levels)
    shift = base_level - min_level

    # 如果已经比 base_level 深，或偏移为负，则不调整（避免标题变浅）
    if shift <= 0:
        return markdown_text

    def replacer(match):
        hashes = match.group(1)
        content = match.group(2)
        new_hashes = '#' * (len(hashes) + shift)
        # 保证不超过 6 级
        if len(new_hashes) > 6:
            new_hashes = '#' * 6
        return f'{new_hashes} {content}'

    return heading_pattern.sub(replacer, markdown_text)


def _process_results_markdown(text: str, base_heading_level: int = 4) -> str:
    """
    专门处理 main_results_and_physics 字段：
    - 修复反斜杠
    - 转换换行（Markdown 强制换行）
    - 调整内部标题层级
    """
    text = _fix_latex_backslashes(text)
    text = _adjust_headings(text, base_level=base_heading_level)
    lines = text.split('\n')
    text = '  \n'.join(lines)
    return text


def _process_text_for_html(text: str) -> str:
    """处理文本用于 HTML 输出：修复反斜杠，转义 HTML，\n -> <br>。"""
    import html
    text = _fix_latex_backslashes(text)
    text = html.escape(text)
    text = text.replace('\n', '<br>\n')
    return text


def _authors_str(authors: List[str]) -> str:
    return ', '.join(authors)


def _make_markdown_section(paper: Dict, heading_base: int = 4) -> str:
    """为单篇论文生成 Markdown 片段。"""
    title = paper.get('title', '无标题')
    authors = _authors_str(paper.get('authors', []))
    date = paper.get('date', '未知')
    doi = paper.get('doi', '')
    page_url = paper.get('page_url', '')
    pdf_url = paper.get('pdf_url', '')
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

    Args:
        papers: 单篇或列表。
        toc: 是否生成目录（多篇时有效）。
        results_heading_base: main_results_and_physics 内部标题的起始级别，默认为4（####）。
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
                anchor = title.replace(' ', '-')
                doc += f"- [{i}. {title}](#{anchor})\n"
            doc += "\n---\n\n"

    for p in papers:
        doc += _make_markdown_section(p, heading_base=results_heading_base)

    return doc


def _make_html_section(paper: Dict) -> str:
    """为单篇论文生成 HTML 片段。"""
    title = _process_text_for_html(paper.get('title', '无标题'))
    authors = _authors_str(paper.get('authors', []))
    date = paper.get('date', '未知')
    doi = paper.get('doi', '')
    page_url = paper.get('page_url', '')
    pdf_url = paper.get('pdf_url', '')
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
    Args:
        papers: 单篇或列表。
        full_document: 是否返回完整的 HTML 文档（含样式）。
    """
    if isinstance(papers, dict):
        papers = [papers]

    body = ""
    for p in papers:
        body += _make_html_section(p)

    if not full_document:
        return body

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


def generate_report(papers: Union[Dict, List[Dict]], format: str = 'markdown',
                    toc: bool = False, full_html: bool = True,
                    results_heading_base: int = 4) -> str:
    """
    统一的报告生成接口。

    Args:
        papers: 单篇论文字典或列表。
        format: 'markdown', 'md' 或 'html'。
        toc: 仅 Markdown，是否生成目录。
        full_html: 仅 HTML，是否生成完整文档。
        results_heading_base: 仅 Markdown，main_results_and_physics 内部标题的起始级别。

    Returns:
        生成的报告字符串。
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
        # 注意：内部包含 Markdown 标题 # 和 ##
        "main_results_and_physics": "# 凝聚形成时间\n泵浦后 180~220\\,fs 建立，指数上升 $\\tau_r = 60\\pm 10$\\,fs。\n\n# 动量分布窄化\nFWHM 从 0.3\\,Å⁻¹ 缩小到 0.1\\,Å⁻¹，符合宏观相干态。\n\n# 退相干机制\n退相干时间约 1.2\\,ps，归因于激子-声子散射。\n\n# 阈值密度\n临界密度 $n_c \\approx 1.2\\times 10^{12}$ cm⁻²，与 BKT 相变一致。",
        "take_home_message": "首次用超快 trARPES 直接观测到激子凝聚的时间动力学，为室温激子器件提供了关键参数。局限在于未能定量分离缺陷对退相干的影响。"
    }

    # 生成 Markdown（自动将 # 标题降为 #### 标题）
    md = generate_report(paper_example, format='markdown', results_heading_base=4)
    print("=== Markdown (标题自动降级) ===")
    print(md)
    
    # 也可以改为从 3 级开始
    md2 = generate_report(paper_example, format='markdown', results_heading_base=3)
    print("\n=== Markdown (标题从 ### 开始) ===")
    print(md2)