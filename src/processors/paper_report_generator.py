"""
paper_report_generator.py (v3)
==============================
根据论文信息字典自动生成 Markdown / HTML 报告。

核心功能：
- 接收单篇或多篇论文的结构化信息（标题、作者、日期、DOI、URL 以及 LLM 生成的总结字段）。
- 通过 Jinja2 模板引擎渲染 ``templates/report/`` 下的 Markdown / HTML 模板，
  Python 端只负责数据预处理（LaTeX 修复、HTML 转义、标题重定级、子领域标签映射等）。
- 模板可由用户直接编辑，无需修改 Python 代码。

模块组成概览：

【辅助函数（private helpers）】
- _fix_latex_backslashes_for_display: 将双反斜杠还原为单反斜杠，修复 LLM 输出中 LaTeX 命令的转义问题（单向，仅用于显示）。
- _process_text_for_markdown: 处理普通文本字段，修复 LaTeX 并将 \\n 转为 Markdown 强制换行（行尾两个空格 + 换行）。
- _process_text_for_html: 处理普通文本字段用于 HTML 输出（修复 LaTeX → HTML 转义 → \\n 替换为 <br>）。
- _adjust_headings: 标题重定级算法——将 Markdown 文本中的内部标题上移/下移若干级别。
- _process_results_markdown: 综合处理所有 LLM 总结字段（修复 LaTeX + 标题重定级 + 换行转换）。
- _authors_str: 将作者列表（List[str]）转换为逗号分隔的字符串。
- _build_subdomain_labels: 子领域 key → 中文短标签固定映射。

【模板基础设施】
- _get_template_env: 懒加载 Jinja2 Environment（FileSystemLoader 指向 REPORT_TEMPLATE_DIR）。
- _load_style_css: 读取 templates/report/html/style.css 内容。

【payload 构造器】
- _make_paper_payload_md: 为 Markdown 模板准备干净的论文字典（_process_results_markdown 预处理）。
- _make_paper_payload_html: 为 HTML 模板准备干净的论文字典（_process_text_for_html 预处理）。

【公共接口（public API）】
- _relevance_legend_md: 报告头部图例 Markdown（薄包装，调模板宏，测试直接调用）。
- _relevance_legend_html: 报告头部图例 HTML（薄包装，调模板宏，测试直接调用）。
- generate_markdown: 生成 Markdown 格式报告（通过 Jinja2 模板渲染，支持多篇论文、目录）。
- generate_html: 生成 HTML 格式报告（通过 Jinja2 模板渲染，支持完整文档模式或纯 body 模式）。
- generate_report: 统一报告生成接口，根据 format 参数路由到 markdown 或 html 生成函数。
"""

from typing import Dict, List, Union, Optional
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import REPORT_TEMPLATE_DIR
from processors.report_presentation import build_report_presentation


# 多领域报告分组（当前未使用，保留供后续扩展）
_UNCLASSIFIED_KEY = "__unclassified__"


# ======================================================================
# 文本处理 helpers（被 payload 构造器调用）
# ======================================================================


def _fix_latex_backslashes_for_display(text: str) -> str:
    """
    将双反斜杠 \\\\ 替换为单反斜杠 \\，恢复 LaTeX 命令用于显示。

    为什么需要这个函数：
    DeepSeek API 的 JSON Output 模式下，LaTeX 命令中的反斜杠（如 \\omega, \\frac）会被 JSON 序列化
    转义为双反斜杠（\\omega, \\frac）。这是因为 JSON 规范要求字符串中的反斜杠用 \\ 表示。
    在生成可读报告时，需要将这些双反斜杠还原为正常的 LaTeX 语法。

    警告：此转换是单向（lossy）的——还原后的文本无法再安全地通过 JSON 序列化往返。
    仅用于最终报告渲染显示场景。

    示例：
    - 输入: "电子能量 \\\\(E = \\\\gamma m c^2\\\\)"  →  输出: "电子能量 \\(E = \\gamma m c^2\\)"
    - 输入: "\\\\(\\\\omega\\\\) 表示激光频率"  →  输出: "\\(\\omega\\) 表示激光频率"
    """
    return text.replace('\\\\', '\\')


def _convert_literal_newlines(text: str) -> str:
    r"""将字面量 ``\n``（反斜杠+n 两个字符）转换为真实换行符。

    背景：LLM 在 JSON Output 模式下偶尔会把换行符写成转义序列 ``\\n``，
    经 ``json.loads`` 解码后变成字面量 ``\n``（反斜杠+n 两个字符）而非真实换行。
    后续按 ``'\n'`` 切行或按行首 ``^#`` 匹配标题的逻辑会因此失效——整段文本
    仍是一行，内部的 ``##`` 标题不在行首，无法被 ``_adjust_headings`` 识别。

    安全约束：只转换反斜杠后紧跟 ``n`` 且 ``n`` 后不跟字母的序列，以避免破坏
    LaTeX 命令（如 ``\nabla``、``\neq``、``\nu``、``\newline`` 等）。

    Parameters
    ----------
    text : str
        可能含有字面量 ``\n`` 的文本。

    Returns
    -------
    str
        字面量 ``\n`` 已转换为真实换行符的文本。
    """
    return re.sub(r'\\n(?![a-zA-Z])', '\n', text)


def _process_text_for_markdown(text: str) -> str:
    """
    处理普通字段用于 Markdown 输出：

    1. 修复 LaTeX 反斜杠（_fix_latex_backslashes）
    2. 将字面量 ``\\n`` 转换为真实换行符（_convert_literal_newlines）
    3. 将 \\n 转换为 Markdown 强制换行：
       Markdown 中，行尾的两个空格后跟换行符表示强制换行（hard line break，类似 <br>）。
       这样 LLM 输出的多行文本在 Markdown 渲染后仍能保持原有的段落和分行结构。

    示例：
    - 输入: "第一行\\n第二行\\n第三行"  →  输出: "第一行  \\n第二行  \\n第三行"
    （注意：每行末尾增加了两个空格，配合换行符形成 Markdown hard break）
    """
    text = _fix_latex_backslashes_for_display(text)
    text = _convert_literal_newlines(text)
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
    - 输入文本: "# 结果\\n## 细节"    base_level=4
    - 检测到 min_level=1，shift=3
    - 输出: "#### 结果\\n##### 细节"

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
    处理 LLM 生成的总结字段用于 Markdown 输出（通用处理）。

    处理步骤（按顺序）：
    1. _fix_latex_backslashes_for_display: 修复 LLM JSON 输出中的双反斜杠
    2. _convert_literal_newlines: 将字面量 ``\\n`` 转换为真实换行符
    3. _adjust_headings: 调整内部标题层级，使其适配报告的主体结构
    4. 将 \\n 转换为 Markdown 强制换行（行尾两个空格 + 换行符）

    为什么所有 LLM 总结字段都需要标题重定级？
    - LLM 可能在任意总结字段（motivation_and_goal、key_setup_and_method、
      main_results_and_physics、take_home_message）中使用 # 或 ## 等高级标题组织内容。
    - 但在报告整体结构中，论文标题本身已用 ## 二级标题，论文内部子标题用 ### 三级标题，
      任何 LLM 输出的标题都应在此基础上进一步缩进（默认 #### 四级起）。
    - 若不统一重定级，LLM 在 key_setup_and_method 等字段中输出的 ## 标题会与论文顶级
      标题同级，破坏文档层次并导致 TOC 错误收录这些子标题（见 20260608 报告缺陷）。
    - 通过 _adjust_headings 重新定位标题级别，确保内部标题不会破坏文档的整体层次结构。

    Parameters
    ----------
    text : str
        LLM 总结字段的原始文本（来自 LLM JSON 输出）
    base_heading_level : int
        内部标题的起始级别，默认为 4（对应 #### 标题）

    Returns
    -------
    str
        处理后的 Markdown 文本
    """
    text = _fix_latex_backslashes_for_display(text)
    text = _convert_literal_newlines(text)
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
    text = _fix_latex_backslashes_for_display(text)
    text = html.escape(text)     # HTML 实体转义，防止注入
    text = text.replace('\n', '<br>\n')
    return text


def _html_escape(text: str) -> str:
    """Escape HTML special characters for safe insertion into HTML output.

    用于短文本字段（journal, authors, doi, date, relevance_category 等），
    这些字段不需要 LaTeX 修复或换行转换，只需转义 HTML 特殊字符。

    Parameters
    ----------
    text : str
        待转义的文本。

    Returns
    -------
    str
        HTML 特殊字符已转义的文本。
    """
    if not text:
        return ""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


def _safe_url(url: str) -> str:
    """Validate URL scheme to prevent XSS via javascript: or data: URIs.

    只允许 http://, https:// 和 mailto: 三种 scheme，
    其他 scheme（javascript:, data:, vbscript: 等）返回空字符串。

    Parameters
    ----------
    url : str
        待验证的 URL。

    Returns
    -------
    str
        验证通过的原 URL，或空字符串（拒绝）。
    """
    if not url:
        return ""
    url = url.strip()
    if url.startswith(("http://", "https://", "mailto:")):
        return url
    return ""


def _authors_str(authors: List[str]) -> str:
    """
    将作者列表转换为逗号分隔的字符串。

    示例：
    - ["张三", "李四", "王五"] → "张三, 李四, 王五"
    - [] → ""
    """
    return ', '.join(authors)


# ======================================================================
# 子领域标签映射
# ======================================================================

# 子领域 key → 中文短标签的固定映射。
#
# 早期实现基于 description 子串匹配（如 "控制"/"AI"/"束流" 等）生成标签，
# 但 description 文本会同时包含多个方向的关键词（例如 plasma_physics 的描述
# 中含有"控制"二字），导致贪婪子串匹配把 plasma_physics 误判为
# "加速器控制与AI"。改为直接按 key 查表，避免歧义。
# 新增子领域时在此处补充一行即可。
_SUBDOMAIN_LABEL_MAP: Dict[str, str] = {
    "acceleration": "加速与后加速",
    "plasma_physics": "等离子体物理与诊断",
    "beam_applications": "束流诊断与辐照",
    "advanced_technology": "束流传输与等离子体光学",
    "laser_wakefield_acceleration": "尾场加速",
}


def _build_subdomain_labels(scope_definition: Dict) -> Dict[str, str]:
    """从 scope_definition 生成子领域中文短标签。

    通过固定的 ``_SUBDOMAIN_LABEL_MAP`` 按 subdomain key 查表得到中文短标签，
    用于在报告元数据中显示。未在映射表中的 key 回退为 key 本身。

    Parameters
    ----------
    scope_definition : dict
        子领域定义字典（来自 ``configs/keywords.yaml`` 的 ``scope_definition``）。

    Returns
    -------
    dict
        ``{subdomain_key: short_label}`` 映射。
    """
    labels = {}
    for key, section in scope_definition.items():
        labels[key] = (
            section.get("display_name")
            or _SUBDOMAIN_LABEL_MAP.get(key, key)
        )
    return labels


# ======================================================================
# 模板基础设施（Jinja2）
# ======================================================================

_template_env_cache: Optional[Environment] = None


def _get_template_env() -> Environment:
    """懒加载 Jinja2 Environment（FileSystemLoader 指向 ``REPORT_TEMPLATE_DIR``）。

    设计要点：
    - **不开启 autoescape**：HTML 转义已由 ``_process_text_for_html`` 完成，
      避免 Jinja2 二次转义导致 ``&lt;`` 等实体被错误转义。
    - ``keep_trailing_newline=True``：保留模板文件末尾的换行符，避免拼接时缺行。
    - ``trim_blocks=True`` / ``lstrip_blocks=True``：消除 Jinja2 标签行对
      空行的干扰，使模板作者更易控制输出格式。
    - 单次进程内复用同一 Environment 以利用 Jinja2 的模板编译缓存。

    Returns
    -------
    Environment
    配置好的 Jinja2 Environment 实例。
    """
    global _template_env_cache
    if _template_env_cache is not None:
        return _template_env_cache
    loader = FileSystemLoader(str(REPORT_TEMPLATE_DIR))
    _template_env_cache = Environment(
        loader=loader,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    _template_env_cache.globals["build_report_presentation"] = build_report_presentation
    return _template_env_cache


def _load_style_css() -> str:
    """读取 ``templates/report/html/style.css`` 原始内容。

    用于内联到完整 HTML 文档的 ``<style>`` 块中。设计目标：让样式修改只
    需编辑单个 CSS 文件，不必改 Python 端。

    Returns
    -------
    str
        CSS 文本（utf-8 解码）。
    """
    css_path = Path(REPORT_TEMPLATE_DIR) / "html" / "style.css"
    return css_path.read_text(encoding="utf-8")


# ======================================================================
# Payload 构造器（Python 端做所有文本处理，模板只负责排版）
# ======================================================================


def _make_paper_payload_md(paper: Dict, scope_definition: Optional[Dict] = None,
                           heading_base: int = 4) -> Dict:
    """为 Markdown 模板准备干净的论文字典。

    文本处理：
    - 普通字段（abstract, one_sentence）走 ``_process_text_for_markdown``。
    - LLM 总结字段（motivation, method, results, take_home, reason）
      走 ``_process_results_markdown(text, heading_base)``，
      完成 LaTeX 修复 + 字面量换行 + 内部标题重定级。

    子领域 key → 中文短标签的映射：
    - 优先使用 ``scope_definition``（来自 ``keywords.yaml``）。
    - 缺失时回退到 ``paper.get('_subdomain_labels', {})``（兼容旧调用方）。

    Parameters
    ----------
    paper : Dict
        原始论文字典。
    scope_definition : dict, optional
        子领域定义字典（``keywords.yaml`` 的 ``scope_definition`` 字段）。
    heading_base : int
        main_results_and_physics 等字段内部标题的起始级别（默认 4）。

    Returns
    -------
    Dict
        模板可直接使用的字段字典（见 templates/report/markdown/paper.md.j2）。
    """
    relevance_reason = paper.get('relevance_reason', '')

    if scope_definition is not None:
        labels = _build_subdomain_labels(scope_definition)
    else:
        labels = paper.get('_subdomain_labels', {})
    matched_subdomains_labels = [
        labels.get(k, k) for k in paper.get('matched_subdomains', [])
    ]

    return {
        'title': paper.get('title', '无标题'),
        'authors': _authors_str(paper.get('authors', [])),
        'date': paper.get('date', '未知') or '未知',
        'doi': paper.get('doi', ''),
        'journal': paper.get('journal', ''),
        'publisher': paper.get('publisher', ''),
        'relevance_category': paper.get('relevance_category', ''),
        'relevance_reason': (
            _process_results_markdown(relevance_reason, heading_base)
            if relevance_reason else ""
        ),
        'relevance_basis': {
            'fulltext': '正文终审',
            'abstract_fallback': '仅标题和摘要（正文不可用）',
            'abstract_clear_reject': '标题和摘要',
        }.get(paper.get('relevance_basis', ''), paper.get('relevance_basis', '')),
        'matched_subdomains_labels': matched_subdomains_labels,
        'page_url': paper.get('page_url', ''),
        'pdf_url': paper.get('pdf_url', ''),
        'abstract': _process_text_for_markdown(paper.get('abstract', '')),
        'one_sentence': _process_text_for_markdown(paper.get('one_sentence', '')),
        'motivation_and_goal': _process_results_markdown(
            paper.get('motivation_and_goal', ''), heading_base),
        'key_setup_and_method': _process_results_markdown(
            paper.get('key_setup_and_method', ''), heading_base),
        'main_results_and_physics': _process_results_markdown(
            paper.get('main_results_and_physics', ''), heading_base),
        'take_home_message': _process_results_markdown(
            paper.get('take_home_message', ''), heading_base),
        'has_full_summary': paper.get('has_full_summary', True),
    }


def _make_paper_payload_html(paper: Dict, scope_definition: Optional[Dict] = None) -> Dict:
    """为 HTML 模板准备干净的论文字典。

    文本处理：所有用户可控字段走 ``_process_text_for_html``（LaTeX 修复 +
    HTML 转义 + \\n→<br>）。标题不重定级（HTML 模式不使用 Markdown 标题语法）。

    子领域标签映射逻辑同 ``_make_paper_payload_md``。

    Parameters
    ----------
    paper : Dict
        原始论文字典。
    scope_definition : dict, optional
        子领域定义字典。

    Returns
    -------
    Dict
        模板可直接使用的字段字典（见 templates/report/html/paper.html.j2）。
    """
    if scope_definition is not None:
        labels = _build_subdomain_labels(scope_definition)
    else:
        labels = paper.get('_subdomain_labels', {})
    matched_subdomains_labels = [
        labels.get(k, k) for k in paper.get('matched_subdomains', [])
    ]

    return {
        'title': _process_text_for_html(paper.get('title', '无标题')),
        'authors': _html_escape(_authors_str(paper.get('authors', []))),
        'date': _html_escape(paper.get('date', '未知') or '未知'),
        'doi': _html_escape(paper.get('doi', '')),
        'journal': _html_escape(paper.get('journal', '')),
        'publisher': _html_escape(paper.get('publisher', '')),
        'relevance_category': _html_escape(paper.get('relevance_category', '')),
        'relevance_reason': _process_text_for_html(
            paper.get('relevance_reason', '')),
        'relevance_basis': _html_escape({
            'fulltext': '正文终审',
            'abstract_fallback': '仅标题和摘要（正文不可用）',
            'abstract_clear_reject': '标题和摘要',
        }.get(paper.get('relevance_basis', ''), paper.get('relevance_basis', ''))),
        'matched_subdomains_labels': matched_subdomains_labels,
        'page_url': _safe_url(paper.get('page_url', '')),
        'pdf_url': _safe_url(paper.get('pdf_url', '')),
        'abstract': _process_text_for_html(paper.get('abstract', '')),
        'one_sentence': _process_text_for_html(paper.get('one_sentence', '')),
        'motivation_and_goal': _process_text_for_html(
            paper.get('motivation_and_goal', '')),
        'key_setup_and_method': _process_text_for_html(
            paper.get('key_setup_and_method', '')),
        'main_results_and_physics': _process_text_for_html(
            paper.get('main_results_and_physics', '')),
        'take_home_message': _process_text_for_html(
            paper.get('take_home_message', '')),
        'has_full_summary': paper.get('has_full_summary', True),
    }


# ======================================================================
# 相关性等级说明（薄包装：测试直接调用，内部委托给模板宏）
# ======================================================================


def _relevance_legend_md() -> str:
    """生成报告头部的相关性等级图例（Markdown blockquote 形式）。

    实际从 ``templates/report/markdown/legend.md.j2`` 加载 ``legend()`` 宏渲染。
    保留为模块级公共函数是为了让测试和外部调用方无需感知模板细节。

    Returns
    -------
    str
        以 ``>`` 引用块开头的多行 Markdown 文本，可直接拼接到报告顶端。
    """
    env = _get_template_env()
    template = env.get_template('markdown/legend.md.j2')
    return template.module.legend(build_report_presentation())


def _relevance_legend_html() -> str:
    """生成报告头部的相关性等级图例（HTML blockquote 形式）。

    实际从 ``templates/report/html/legend.html.j2`` 加载 ``legend()`` 宏渲染。
    视觉样式由 ``templates/report/html/style.css`` 中的
    ``blockquote.relevance-legend`` 块控制。

    Returns
    -------
    str
        ``<blockquote>`` 片段，可直接拼接到 HTML 报告 body 顶端。
    """
    env = _get_template_env()
    template = env.get_template('html/legend.html.j2')
    return template.module.legend(build_report_presentation())


# ======================================================================
# 报告排序
# ======================================================================

# 相关性等级 → 排序优先级（A 最先；空值/未知排末尾）。
# 与 Phase E LLM Prompt 的 A/B/C/D 分类对应。
_RELEVANCE_RANK: Dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3}


def _sort_papers(papers: List[Dict]) -> List[Dict]:
    """
    按「相关性等级 → 日期倒序」对论文列表排序（就地修改，返回同一列表）。

    排序规则（2026-07-25 起）：
    1. 一级 key：``relevance_category``，A → B → C → D 顺序；
       缺字段或未知值（A/B/C/D 之外）排到末尾，不影响其他论文。
    2. 二级 key：``date`` 字符串倒序（最新在前）；空日期排到该 category 末尾。
       直接对 ISO 日期字符串（YYYY-MM-DD）做字符串倒序等同于时间倒序，
       无需 datetime 解析。

    使用 Python ``list.sort`` 的稳定性：先按 date 倒序排，再按 category
    升序排，二次 sort 不打乱同 category 内的 date 顺序。

    Parameters
    ----------
    papers : list of dict
        论文字典列表（每项需含 ``relevance_category`` 与 ``date`` 字段，
        缺则用空字符串兜底）。

    Returns
    -------
    list of dict
        排序后的同一列表（in-place + return，便于链式调用）。
    """
    # 一级：date 倒序（字符串字典序与时间序一致，前缀越长越新越靠前）
    papers.sort(key=lambda p: p.get("date", "") or "", reverse=True)
    # 二级：relevance_category 升序（rank 越小越靠前，未知 rank=99 排末位）
    papers.sort(key=lambda p: _RELEVANCE_RANK.get(p.get("relevance_category", "") or "", 99))
    return papers


# ======================================================================
# Markdown 生成（通过 Jinja2 模板渲染）
# ======================================================================


def generate_markdown(papers: Union[Dict, List[Dict]], toc: bool = False,
                      results_heading_base: int = 4,
                      scope_definition: Optional[Dict] = None,
                      presentation: Optional[Dict] = None) -> str:
    """生成 Markdown 格式的报告。

    渲染 ``templates/report/markdown/document.md.j2``，模板负责：
    1. 头部相关性等级图例（始终在最前）。
    2. 多篇论文时的 ``# 文献报告`` 一级标题 + 可选 ``## 目录``。
    3. 循环渲染每篇论文（``markdown/paper.md.j2`` 的 ``paper()`` 宏）。

    Python 端仅做数据预处理：文本处理 + 子领域标签映射。

    Args:
        papers: 单篇论文字典或列表。
        toc: 是否生成目录（仅在 papers 为多篇列表时生效）。
        results_heading_base: main_results_and_physics 内部标题的起始级别（默认 4）。
        scope_definition: dict, optional
            子领域定义字典（来自 keywords.yaml 的 ``scope_definition`` 字段）。
            传入后用于生成子领域中文短标签。

    Returns:
        生成的 Markdown 报告字符串。
    """
    if isinstance(papers, dict):
        papers = [papers]
    # 统一排序：相关性等级 A 先 → 同级日期倒序（详见 _sort_papers 注释）
    _sort_papers(papers)
    payloads = [
        _make_paper_payload_md(p, scope_definition=scope_definition,
                               heading_base=results_heading_base)
        for p in papers
    ]
    env = _get_template_env()
    template = env.get_template('markdown/document.md.j2')
    presentation = presentation or build_report_presentation(scope_definition, papers)
    return template.render(papers=payloads, toc=toc, presentation=presentation)


# ======================================================================
# HTML 生成（通过 Jinja2 模板渲染）
# ======================================================================


def generate_html(papers: Union[Dict, List[Dict]], full_document: bool = True,
                  scope_definition: Optional[Dict] = None,
                  presentation: Optional[Dict] = None) -> str:
    """生成 HTML 格式的报告。

    渲染 ``templates/report/html/document.html.j2``：
    - ``full_document=True`` 时输出完整 HTML5 文档（含 ``<!DOCTYPE>``、``<head>``、
      内联 ``<style>{{ style_css }}</style>``），CSS 来自
      ``templates/report/html/style.css``。
    - ``full_document=False`` 时仅返回 body 内部内容（适合嵌入到已有页面）。

    Args:
        papers: 单篇论文字典或列表。
        full_document: 是否返回完整 HTML 文档。
                       设为 False 时仅返回 body 内部内容。
        scope_definition: dict, optional
            子领域定义字典。

    Returns:
        生成的 HTML 报告字符串。
    """
    if isinstance(papers, dict):
        papers = [papers]
    # 统一排序：相关性等级 A 先 → 同级日期倒序（详见 _sort_papers 注释）
    _sort_papers(papers)
    payloads = [
        _make_paper_payload_html(p, scope_definition=scope_definition)
        for p in papers
    ]
    style_css = _load_style_css() if full_document else ""
    env = _get_template_env()
    template = env.get_template('html/document.html.j2')
    presentation = presentation or build_report_presentation(scope_definition, papers)
    return template.render(papers=payloads, full_document=full_document,
                           style_css=style_css, presentation=presentation)


# ======================================================================
# 统一报告生成接口
# ======================================================================


def generate_report(papers: Union[Dict, List[Dict]], format: str = 'markdown',
                    toc: bool = False, full_html: bool = True,
                    results_heading_base: int = 4,
                    scope_definition: Optional[Dict] = None,
                    presentation: Optional[Dict] = None) -> str:
    """统一的报告生成接口。

    根据 ``format`` 参数自动路由到 Markdown 或 HTML 生成函数。

    Args:
        papers: 单篇论文字典或列表。字典需包含 title, authors, one_sentence 等字段。
        format: 输出格式，支持 'markdown', 'md', 'html'。
        toc: 仅 Markdown 格式生效。是否在多篇论文时生成目录。
        full_html: 仅 HTML 格式生效。是否返回完整 HTML 文档（含 CSS 样式和 head 元信息）。
        results_heading_base: 仅 Markdown 格式生效。main_results_and_physics 内部标题的起始级别，默认为 4。
        scope_definition: dict, optional
            子领域定义字典（来自 keywords.yaml 的 ``scope_definition`` 字段）。
            传入后用于生成子领域中文短标签。

    Returns:
        生成的报告字符串。

    Raises:
        ValueError: 当 format 参数不是 'markdown', 'md', 'html' 之一时抛出。
    """
    fmt = format.lower()
    if fmt in ('markdown', 'md'):
        return generate_markdown(
            papers, toc=toc,
            results_heading_base=results_heading_base,
            scope_definition=scope_definition,
            presentation=presentation,
        )
    elif fmt == 'html':
        return generate_html(
            papers, full_document=full_html,
            scope_definition=scope_definition,
            presentation=presentation,
        )
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
        "journal": "Nature Physics",
        "publisher": "Nature",
        "matched_subdomains": ["acceleration"],
        "relevance_category": "A",
        "relevance_reason": "使用 \\nabla B 约束输运方法。",
        "one_sentence": "本文采用时间分辨角分辨光电子能谱（trARPES），研究了单层WSe₂中激子凝聚的动力学过程，得到了凝聚体形成时间约为 200\\,fs 的核心结论。",
        "motivation_and_goal": "激子凝聚是否在室温下存在仍存争议。\\citet{ref1} 报道了稳态信号，但缺少超快动力学证据。本文目标：直接观测凝聚形成与退相干的时间尺度。",
        "key_setup_and_method": "使用 800\\,nm 泵浦、极紫外探测的 trARPES 系统，时间分辨率 50\\,fs。样品为 hBN 封装的单层 WSe₂，温度 80\\,K。核心公式：\\Delta n(k,t) \\propto |\\psi(k,t)|^2。",
        # 注意：内部包含 Markdown 标题 # 和 ##——在生成报告时会通过 _adjust_headings 自动重定级
        "main_results_and_physics": "# 凝聚形成时间\n泵浦后 180~220\\,fs 建立，指数上升 $\\tau_r = 60\\pm 10$\\,fs。\n\n# 动量分布窄化\nFWHM 从 0.3\\,Å⁻¹ 缩小到 0.1\\,Å⁻¹，符合宏观相干态。\n\n# 退相干机制\n退相干时间约 1.2\\,ps，归因于激子-声子散射。\n\n# 阈值密度\n临界密度 $n_c \\approx 1.2\\times 10^{12}$ cm⁻²，与 BKT 相变一致。",
        "take_home_message": "首次用超快 trARPES 直接观测到激子凝聚的时间动力学，为室温激子器件提供了关键参数。局限在于未能定量分离缺陷对退相干的影响。"
    }
    scope = {
        "acceleration": {"description": "本方向研究高功率激光与靶相互作用驱动离子加速。", "topics": []},
    }

    # 生成 Markdown（自动将 # 标题降为 #### 标题）
    # _adjust_headings 检测到内部 min_level=1, base_level=4 → shift=3 → # → ####
    md = generate_report(paper_example, format='markdown',
                         results_heading_base=4, scope_definition=scope)
    print("=== Markdown (标题自动降级) ===")
    print(md)

    # 也可以改为从 3 级开始
    # _adjust_headings 检测到内部 min_level=1, base_level=3 → shift=2 → # → ###
    md2 = generate_report(paper_example, format='markdown',
                          results_heading_base=3, scope_definition=scope)
    print("\n=== Markdown (标题从 ### 开始) ===")
    print(md2)
