"""
测试: 报告生成 (paper_report_generator.py)

覆盖范围:
  - Markdown 报告生成 (单篇、多篇、目录)
  - HTML 报告生成 (片段、完整文档)
  - LaTeX 反斜杠修复
  - Markdown 内部标题层级调整
  - 作者列表格式化
  - 空字段容错
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from processors.paper_report_generator import (
    generate_report,
    generate_markdown,
    generate_html,
    _build_subdomain_labels,
    _fix_latex_backslashes_for_display,
    _adjust_headings,
    _process_results_markdown,
    _authors_str,
    _relevance_legend_md,
    _relevance_legend_html,
    _sort_papers,
)


# ---- 测试数据 ----

_SCOPE_DEFINITION = {
    "acceleration": {
        "description": "本方向研究高功率激光与固体/气体靶相互作用驱动离子加速。",
        "topics": ["TNSA", "RPA"],
    },
    "plasma_physics": {
        "description": "本方向研究超强激光与等离子体相互作用的基础物理。",
        "topics": ["Self-focusing", "Plasma channel"],
    },
}


def _sample_paper(**overrides):
    """返回一个完整的示例论文字典，支持字段覆盖。"""
    paper = {
        "title": "用超快光谱探测二维材料中的激子凝聚",
        "authors": ["张三", "李四", "王五"],
        "date": "2025-04-15",
        "doi": "10.1234/example.2025.001",
        "page_url": "https://journal.example.com/article/001",
        "pdf_url": "https://journal.example.com/article/001/pdf",
        "abstract": "本文利用时间分辨角分辨光电子能谱研究了单层WSe₂中的激子凝聚现象。",
        "one_sentence": "本文采用 trARPES 研究了单层 WSe₂ 中激子凝聚的动力学过程。",
        "motivation_and_goal": "激子凝聚是否在室温下存在仍存争议。",
        "key_setup_and_method": "使用 800nm 泵浦、极紫外探测的 trARPES 系统。",
        "main_results_and_physics": "## 凝聚形成时间\n泵浦后 180~220 fs 建立。\n\n## 动量分布窄化\nFWHM 缩小。",
        "take_home_message": "首次用超快 trARPES 直接观测到激子凝聚的时间动力学。",
        "matched_subdomains": [],
        "journal": "Nature Physics",
        "publisher": "Nature",
        "discovery_source": "rss",
    }
    paper.update(overrides)
    return paper


# ---- LaTeX 辅助函数 ----

def test_fix_latex_backslashes():
    """双反斜杠应转为单反斜杠。"""
    text = "\\\\omega = 2\\\\pi f"
    fixed = _fix_latex_backslashes_for_display(text)
    assert fixed == "\\omega = 2\\pi f"


def test_fix_latex_no_backslashes():
    """无反斜杠的文本应保持不变。"""
    text = "No special chars"
    assert _fix_latex_backslashes_for_display(text) == text


# ---- 标题调整 ----

def test_adjust_headings_base_level_4():
    """内部 # 标题应调整为 ####。"""
    md = "# Results\n## Detail\nText"
    result = _adjust_headings(md, base_level=4)
    assert "#### Results" in result
    assert "##### Detail" in result


def test_adjust_headings_no_headings():
    """无标题文本原样返回。"""
    text = "Plain text without any headings"
    assert _adjust_headings(text, 4) == text


def test_adjust_headings_already_deeper():
    """已经是深层级标题不需要调整。"""
    text = "##### Very deep"
    result = _adjust_headings(text, base_level=4)
    assert result == text  # 不需要动


# ---- 结果处理 ----

def test_process_results_markdown():
    """验证 main_results 字段的完整处理流程。"""
    text = "## Result 1\nKey finding with $E=mc^2$"
    processed = _process_results_markdown(text, base_heading_level=4)
    # 应有换行处理
    assert "Result 1" in processed
    # 公式反斜杠应修复
    assert "E=mc^2" in processed


def test_process_results_markdown_literal_newline():
    r"""验证字面量 \n（反斜杠+n）被转换为真实换行，内部标题能被重定级。

    复现 20260713 报告第 1 篇论文 main_results_and_physics 字段的缺陷：
    LLM 在 JSON 中输出 \\n（双反斜杠+n），json.loads 解码后变成字面量 \n
    （反斜杠+n 两个字符），而非真实换行。导致整段文本仍是一行，内部的
    ## 标题不在行首，_adjust_headings 的 ^#{1,6} 正则无法匹配。
    """
    # 字面量 \n（反斜杠+n 两个字符），不是真实换行
    text = "## 主要结果\\n## 细节"
    processed = _process_results_markdown(text, base_heading_level=4)
    # 字面量 \n 应被转换为真实换行，标题应被重定级到 ####
    assert "#### 主要结果" in processed
    assert "#### 细节" in processed
    # 不应残留字面量 \n
    assert "\\n" not in processed


def test_convert_literal_newlines_preserves_latex():
    r"""验证 \n 后跟字母时不被转换，保护 LaTeX 命令如 \nabla、\neq、\nu。"""
    from processors.paper_report_generator import _convert_literal_newlines
    # \nabla \neq \nu 应原样保留（\n 后跟字母）
    assert _convert_literal_newlines(r"\nabla \neq \nu") == r"\nabla \neq \nu"
    # \n 后跟字母 b 不应转换
    assert _convert_literal_newlines("a\\nb") == "a\\nb"
    # \n 后跟空格/标点/行尾应转换为真实换行
    assert _convert_literal_newlines("a\\n b") == "a\n b"
    assert _convert_literal_newlines("a\\n") == "a\n"
    assert _convert_literal_newlines("a\\n, b") == "a\n, b"


# ---- 作者格式化 ----

def test_authors_str():
    """作者列表正确格式化。"""
    assert _authors_str(["Alice", "Bob"]) == "Alice, Bob"
    assert _authors_str([]) == ""
    assert _authors_str(["Single"]) == "Single"


# ---- Markdown 报告 ----

def test_generate_markdown_single_paper():
    """生成单篇 Markdown 报告。"""
    paper = _sample_paper()
    md = generate_report(paper, format="markdown")

    assert "超快光谱" in md
    assert "张三" in md
    assert "2025-04-15" in md
    assert "10.1234/example.2025.001" in md
    assert "### 研究动机与目标" in md
    assert "### 关键方法与设置" in md
    assert "### 主要结果与物理内涵" in md
    assert "### 要点总结" in md


def test_generate_markdown_multiple_papers():
    """生成多篇 Markdown 报告。"""
    papers = [_sample_paper(), _sample_paper()]
    papers[1]["title"] = "第二篇论文"
    md = generate_report(papers, format="markdown", toc=True)

    assert "# 文献报告" in md
    assert "## 目录" in md
    assert "超快光谱" in md
    assert "第二篇论文" in md


def test_generate_markdown_empty_fields():
    """空字段不应导致错误。"""
    paper = {
        "title": "Test",
        "authors": [],
        "date": "",
        "doi": "",
        "page_url": "",
        "pdf_url": "",
        "one_sentence": "",
        "motivation_and_goal": "",
        "key_setup_and_method": "",
        "main_results_and_physics": "",
        "take_home_message": "",
    }
    md = generate_report(paper, format="markdown")
    assert "Test" in md
    # 空日期在报告中显示为空或空格，不是 "未知"


# ---- HTML 报告 ----

def test_generate_html_single_paper():
    """生成单篇 HTML 报告。"""
    paper = _sample_paper()
    html = generate_report(paper, format="html")

    assert "<!DOCTYPE html>" in html
    assert "超快光谱" in html
    assert "张三" in html


def test_generate_html_fragment():
    """生成 HTML 片段（非完整文档）。"""
    paper = _sample_paper()
    html = generate_html([paper], full_document=False)

    assert "<!DOCTYPE html>" not in html
    assert "<section>" in html
    assert "超快光谱" in html


# ---- 子领域标签映射 ----

_SCOPE_DEF_FOR_LABELS = {
    "acceleration": {
        "description": "本方向研究高功率激光与固体/气体靶相互作用驱动离子和质子加速。",
    },
    "plasma_physics": {
        "description": "本方向研究超强激光与等离子体相互作用的基础物理与诊断技术。",
    },
    "beam_applications": {
        "description": "本方向关注激光加速束流的诊断、探测和应用。",
    },
    "advanced_technology": {
        "description": "本方向研究高梯度束流传输与操控技术、等离子体光学元件以及AI。",
    },
}


def test_build_subdomain_labels_known():
    """已知子领域应返回正确的中文短标签。"""
    labels = _build_subdomain_labels(_SCOPE_DEF_FOR_LABELS)
    assert labels.get("acceleration") == "加速与后加速"
    assert labels.get("plasma_physics") == "等离子体物理与诊断"
    assert labels.get("beam_applications") == "束流诊断与辐照"
    assert labels.get("advanced_technology") == "束流传输与等离子体光学"


def test_build_subdomain_labels_empty():
    """空 scope_definition 返回空字典。"""
    assert _build_subdomain_labels({}) == {}


def test_build_subdomain_labels_fallback_key():
    """无法识别的描述应返回原始 key 作为标签。"""
    labels = _build_subdomain_labels({"custom": {"description": "一些自定义研究内容"}})
    assert labels.get("custom") == "custom"


# ---- 元数据新顺序 + 字段删除（2026-07-25）----

def test_report_displays_dynamic_subdomain_metadata():
    """报告使用配置生成的中文标签恢复显示相关方向。"""
    papers = [
        _sample_paper(matched_subdomains=["acceleration", "plasma_physics"],
                      title="Paper A"),
    ]
    md = generate_report(papers, format="markdown", toc=True,
                         scope_definition=_SCOPE_DEF_FOR_LABELS)
    assert "**相关方向**" in md
    assert "加速与后加速" in md
    assert "等离子体物理与诊断" in md


def test_report_abstract_fallback_omits_empty_technical_sections():
    """摘要降级论文不得伪装成已有完整技术总结。"""
    paper = _sample_paper(
        relevance_category="B",
        relevance_basis="abstract_fallback",
        has_full_summary=False,
        matched_subdomains=["acceleration"],
    )
    md = generate_report(
        [paper], format="markdown", scope_definition=_SCOPE_DEF_FOR_LABELS,
    )
    assert "仅标题和摘要（正文不可用）" in md
    assert "无正文，无法生成详细总结" in md
    assert "### 研究动机与目标" not in md
    assert "### 主要结果与物理内涵" not in md


def test_decision_summary_does_not_add_paper_heading():
    """决策摘要不得增加会被 WebUI 误计为论文的二级标题。"""
    md = generate_report(
        [_sample_paper(relevance_category="A")], format="markdown",
    )
    assert "**本期决策摘要**" in md
    assert "## 本期决策摘要" not in md


def test_report_no_publisher_no_pdf_in_metadata():
    """删除「出版社」与「PDF」字段（2026-07-25 调整后只剩 期刊）。"""
    md = generate_report([_sample_paper()], format="markdown", toc=False)
    assert "**出版社**" not in md
    assert "**PDF**" not in md
    html = generate_report([_sample_paper()], format="html", full_html=True)
    assert "<strong>出版社:</strong>" not in html
    assert "<strong>PDF:</strong>" not in html


def test_report_metadata_new_order():
    """新元信息顺序：期刊 → 作者 → 日期 → DOI → 页面 → 相关性等级 → 判断理由 → 原文摘要 → 一句话。"""
    md = generate_report([_sample_paper(relevance_category="A",
                                         relevance_reason="直接相关")],
                         format="markdown", toc=False)
    # 抽取 title 行之后到「原文摘要」之前的元信息行
    lines = md.split("\n")
    meta_lines = []
    for line in lines:
        if line.startswith("## "):
            continue
        if line.startswith("**") or line.startswith("**"):
            meta_lines.append(line)
        if line.startswith("**原文摘要**"):
            break
    # 各字段在元信息中的索引应符合新顺序
    def idx_of(label):
        for i, l in enumerate(meta_lines):
            if l.startswith(f"**{label}**:"):
                return i
        return -1

    journal_i = idx_of("期刊")
    author_i = idx_of("作者")
    date_i = idx_of("日期")
    doi_i = idx_of("DOI")
    page_i = idx_of("页面")
    cat_i = idx_of("相关性等级")
    reason_i = idx_of("判断理由")
    assert journal_i == 0, f"期刊 应在第一位，实际 idx={journal_i}"
    assert -1 < author_i < date_i < doi_i < page_i < cat_i < reason_i, \
        f"顺序错误: 期刊={journal_i} 作者={author_i} 日期={date_i} " \
        f"DOI={doi_i} 页面={page_i} 相关性等级={cat_i} 判断理由={reason_i}"


def test_report_html_metadata_new_order():
    """HTML 报告元信息顺序与 Markdown 一致。"""
    html = generate_report([_sample_paper(relevance_category="A",
                                            relevance_reason="直接相关")],
                           format="html", full_html=False)
    # 在 <h2> 标题之后找 <p>...</p> 元信息块
    p_start = html.find("<h2>")
    p_end = html.find("</p>", p_start)
    p_block = html[p_start:p_end]
    journal_i = p_block.find("<strong>期刊:</strong>")
    author_i = p_block.find("<strong>作者:</strong>")
    date_i = p_block.find("<strong>日期:</strong>")
    doi_i = p_block.find("<strong>DOI:</strong>")
    page_i = p_block.find("<strong>页面:</strong>")
    cat_i = p_block.find("<strong>相关性等级:</strong>")
    reason_i = p_block.find("<strong>判断理由:</strong>")
    assert journal_i >= 0
    assert journal_i < author_i < date_i < doi_i < page_i < cat_i < reason_i, \
        f"HTML 顺序错误: 期刊={journal_i} 作者={author_i} 日期={date_i} " \
        f"DOI={doi_i} 页面={page_i} 相关性等级={cat_i} 判断理由={reason_i}"


def test_report_later_sections_unchanged():
    """H3 子节（研究动机/方法/结果/要点）顺序与文本保持不变。"""
    md = generate_report([_sample_paper()], format="markdown", toc=False)
    sections = ["### 研究动机与目标", "### 关键方法与设置",
                "### 主要结果与物理内涵", "### 要点总结"]
    indices = [md.find(s) for s in sections]
    assert all(i > 0 for i in indices), f"子节缺失: {dict(zip(sections, indices))}"
    assert indices == sorted(indices), f"子节顺序错乱: {dict(zip(sections, indices))}"


# ---- 排序（2026-07-25 起：相关性等级 A 先 → 同级日期倒序）----

def test_sort_papers_by_relevance_then_date_desc():
    """_sort_papers 应把 A 排在 B 前；同级内日期倒序（最新在前）。"""
    papers = [
        _sample_paper(title="B-old", relevance_category="B", date="2025-01-01"),
        _sample_paper(title="A-new", relevance_category="A", date="2025-06-15"),
        _sample_paper(title="A-old", relevance_category="A", date="2025-03-10"),
        _sample_paper(title="B-new", relevance_category="B", date="2025-12-01"),
    ]
    _sort_papers(papers)
    titles = [p["title"] for p in papers]
    # A 组（2 篇）应在 B 组（2 篇）之前；A 内日期倒序；B 内日期倒序
    assert titles == ["A-new", "A-old", "B-new", "B-old"], f"实际顺序: {titles}"


def test_sort_papers_unknown_category_goes_last():
    """未知 category（如空字符串或 'X'）排到末尾，不影响其他论文。"""
    papers = [
        _sample_paper(title="X", relevance_category="X", date="2025-06-15"),
        _sample_paper(title="A", relevance_category="A", date="2025-01-01"),
        _sample_paper(title="empty", relevance_category="", date="2025-12-01"),
    ]
    _sort_papers(papers)
    titles = [p["title"] for p in papers]
    # A 应在前，未知排后；空字符串视为未知
    assert titles[0] == "A", f"A 应在首位，实际 {titles}"
    # 未知组内维持 date 倒序
    assert titles[1] in ("X", "empty") and titles[2] in ("X", "empty"), titles


def test_sort_papers_empty_date_goes_last_in_category():
    """同 category 内空日期排到该 category 末尾。"""
    papers = [
        _sample_paper(title="A-no-date", relevance_category="A", date=""),
        _sample_paper(title="A-old", relevance_category="A", date="2025-01-01"),
        _sample_paper(title="A-new", relevance_category="A", date="2025-06-15"),
    ]
    _sort_papers(papers)
    titles = [p["title"] for p in papers]
    assert titles == ["A-new", "A-old", "A-no-date"], f"实际: {titles}"


def test_report_uses_relevance_first_sort():
    """端到端：传入乱序 papers，generate_report 内部排序后再渲染。"""
    papers = [
        _sample_paper(title="B-paper", relevance_category="B", date="2025-12-01"),
        _sample_paper(title="A-paper", relevance_category="A", date="2025-06-15"),
    ]
    md = generate_report(papers, format="markdown", toc=False)
    a_idx = md.find("## A-paper")
    b_idx = md.find("## B-paper")
    assert a_idx < b_idx, f"A 论文应在 B 前：A={a_idx} B={b_idx}"


# ---- 相关性元信息 ----

def test_report_shows_relevance_category_and_reason():
    """传入 relevance_category / relevance_reason 时，元信息行应同时出现。"""
    papers = [
        _sample_paper(
            relevance_category="A",
            relevance_reason="本文研究 LWFA 电子注入机制，与本组方向核心相关。",
        ),
    ]
    md = generate_report(papers, format="markdown", toc=True)
    assert "**相关性等级**: A" in md
    assert "**判断理由**: 本文研究 LWFA 电子注入机制" in md
    # LLM 文本中可能的 LaTeX 应被保留为反斜杠形式（_fix_latex_backslashes）
    papers_latex = [
        _sample_paper(
            relevance_category="B",
            relevance_reason="使用 \\nabla B 约束输运，与束流诊断间接相关。",
        ),
    ]
    md_latex = generate_report(papers_latex, format="markdown", toc=True)
    assert "**相关性等级**: B" in md_latex
    assert "\\nabla B" in md_latex  # 反斜杠未被错误吞掉


def test_report_missing_relevance_fields_omits_lines():
    """未提供 relevance_category / relevance_reason 时论文块不应出现对应元信息行。

    注意：报告头部图例也包含「相关性等级」一词（作为术语），因此本断言针对论文
    块内 meta info 的冒号格式 `**相关性等级**:` / `**判断理由**:`。
    """
    md = generate_report([_sample_paper()], format="markdown", toc=True)
    # 论文块 meta info（冒号格式）不应出现
    assert "**相关性等级**:" not in md
    assert "**判断理由**:" not in md
    # 报告头部图例（说明术语）仍应存在
    assert "**相关性等级说明**" in md


def test_html_shows_relevance_category_and_reason():
    """HTML 报告也应同时渲染 相关性等级 / 判断理由。"""
    papers = [
        _sample_paper(
            relevance_category="A",
            relevance_reason="& <b>核心</b>相关 <script>alert(1)</script>",
        ),
    ]
    html = generate_html(papers, full_document=False)
    assert "<strong>相关性等级:</strong> A" in html
    assert "<strong>判断理由:</strong>" in html
    # XSS 防护：reason 中的 HTML 标签必须被转义
    assert "&lt;b&gt;核心&lt;/b&gt;" in html
    assert "<script>alert(1)</script>" not in html


# ---- 报告头部图例 ----

def test_relevance_legend_md_contains_all_levels():
    """Markdown 图例应包含 A/B/C/D 四级完整定义（2026-07-25 起不再标注来源）。"""
    md = _relevance_legend_md()
    for level, short, _ in [
        ("A", "直接相关", ""),
        ("B", "间接相关", ""),
        ("C", "同领域但距离远", ""),
        ("D", "不相关", ""),
    ]:
        assert f"> - **{level}**（{short}）" in md, f"missing level {level}"
    # 必须以 > blockquote 形式呈现
    assert md.startswith("> ")
    # 2026-07-25 起不再标注来源路径
    assert "relevance.yaml" not in md
    assert "Phase E LLM Prompt" not in md


def test_relevance_legend_html_contains_all_levels():
    """HTML 图例应包含 A/B/C/D 四级完整定义（2026-07-25 起不再标注来源）。"""
    html = _relevance_legend_html()
    assert "<blockquote" in html
    for level, short, _ in [
        ("A", "直接相关", ""),
        ("B", "间接相关", ""),
        ("C", "同领域但距离远", ""),
        ("D", "不相关", ""),
    ]:
        assert f"<strong>{level}</strong>（{short}）" in html
    assert "relevance.yaml" not in html
    assert "Phase E LLM Prompt" not in html


# ---- 报告排序说明（2026-07-25 起，最顶端）----

def test_report_sort_note_appears_at_top_markdown():
    """Markdown 报告最顶端应有「报告排序」说明，位于相关性等级图例之前。"""
    md = generate_report([_sample_paper()], format="markdown", toc=False)
    sort_idx = md.find("> **报告排序**")
    legend_idx = md.find("> **相关性等级说明**")
    disclaimers_idx = md.find("> **其他说明**")
    paper_idx = md.find("## ")
    assert sort_idx == 0, f"排序说明应在第 0 字符，实际 idx={sort_idx}"
    assert 0 <= sort_idx < legend_idx < disclaimers_idx < paper_idx, \
        f"顺序错乱: 排序={sort_idx} 图例={legend_idx} 说明={disclaimers_idx} 首篇={paper_idx}"


def test_report_disclaimers_contain_three_points():
    """报告头部「其他说明」应包含 3 条用户关心的局限性说明。"""
    md = generate_report([_sample_paper()], format="markdown", toc=False)
    # 3 条必含关键词
    assert "筛选 prompt 调整" in md, "缺少 prompt 调整说明"
    assert "RSS 历史回溯" in md, "缺少 RSS 回溯说明"
    assert "仅以摘要" in md, "缺少摘要局限性说明"
    # HTML 端
    html = generate_report([_sample_paper()], format="html", full_html=True)
    assert "筛选 prompt 调整" in html
    assert "RSS 历史回溯" in html
    assert "仅以摘要" in html


def test_report_sort_note_appears_at_top_html():
    """HTML 报告最顶端应有「报告排序」blockqute，位于 legend 与首个 <section> 之前。"""
    html = generate_report([_sample_paper()], format="html", full_html=True)
    # 用 blockquote 标签的完整 class 属性匹配，避免与 CSS 规则中的
    # ``blockquote.sort-note { ... }`` 子串混淆。
    sort_idx = html.find('<blockquote class="sort-note">')
    legend_idx = html.find('<blockquote class="relevance-legend">')
    disclaimers_idx = html.find('<blockquote class="disclaimers">')
    section_idx = html.find("<section>")
    assert 0 <= sort_idx < legend_idx < disclaimers_idx < section_idx, \
        f"HTML 顺序错乱: 排序={sort_idx} 图例={legend_idx} 说明={disclaimers_idx} 首篇={section_idx}"


def test_markdown_report_includes_legend_at_top():
    """Markdown 报告（多篇）开头应是相关性等级图例，置于 # 文献报告 之前。"""
    papers = [_sample_paper(title="Paper A"), _sample_paper(title="Paper B", doi="10.1234/b")]
    md = generate_report(papers, format="markdown", toc=True)
    legend_idx = md.find("> **相关性等级说明**")
    title_idx = md.find("# 文献报告")
    paper_idx = md.find("## Paper A")
    assert 0 <= legend_idx < title_idx < paper_idx, \
        "legend must precede report title and first paper"


def test_markdown_single_paper_report_includes_legend():
    """单篇 Markdown 报告也应包含图例（无 # 文献报告 一级标题时仍存在）。"""
    md = generate_report(_sample_paper(title="Solo"), format="markdown", toc=False)
    assert "> **相关性等级说明**" in md
    assert "直接研究课题组核心方向" in md


def test_html_report_includes_legend_at_top():
    """HTML 报告开头应是相关性等级图例 blockquote，置于第一个 <section> 之前。"""
    papers = [_sample_paper(title="Paper A"), _sample_paper(title="Paper B", doi="10.1234/b")]
    html = generate_report(papers, format="html", full_html=True)
    legend_idx = html.find("相关性等级说明")
    section_idx = html.find("<section>")
    assert 0 <= legend_idx < section_idx, "legend must precede first section"
    # blockquote 标签存在
    assert 'class="relevance-legend"' in html


def test_html_legend_fragment_includes_legend():
    """非完整 HTML 片段（full_document=False）也应包含图例。"""
    html = generate_html([_sample_paper()], full_document=False)
    assert "<blockquote" in html
    assert "相关性等级说明" in html


# ---- 异常 ----

def test_generate_report_invalid_format():
    """不支持的格式应抛出 ValueError。"""
    import pytest
    with pytest.raises(ValueError):
        generate_report([_sample_paper()], format="docx")


# ---- 模板外置 ----

def test_template_files_exist():
    """12 个外置模板文件必须全部存在（Markdown/HTML 各 5 个 + style.css + explained.html）。"""
    from pathlib import Path
    from config import REPORT_TEMPLATE_DIR
    expected = [
        "markdown/legend.md.j2",
        "markdown/paper.md.j2",
        "markdown/document.md.j2",
        "markdown/sort_note.md.j2",
        "markdown/disclaimers.md.j2",
        "html/legend.html.j2",
        "html/paper.html.j2",
        "html/document.html.j2",
        "html/sort_note.html.j2",
        "html/disclaimers.html.j2",
        "html/explained.html.j2",
        "html/style.css",
    ]
    for rel in expected:
        path = REPORT_TEMPLATE_DIR / rel
        assert path.exists(), f"missing template file: {rel}"
        assert path.stat().st_size > 0, f"empty template file: {rel}"


def test_template_env_loads_all_templates():
    """Jinja2 Environment 加载器应能成功加载全部 .j2 模板。"""
    from processors.paper_report_generator import _get_template_env
    env = _get_template_env()
    for name in [
        "markdown/legend.md.j2",
        "markdown/paper.md.j2",
        "markdown/document.md.j2",
        "markdown/sort_note.md.j2",
        "markdown/disclaimers.md.j2",
        "html/legend.html.j2",
        "html/paper.html.j2",
        "html/document.html.j2",
        "html/sort_note.html.j2",
        "html/disclaimers.html.j2",
        "html/explained.html.j2",
    ]:
        tpl = env.get_template(name)
        assert tpl is not None


def test_template_legend_contains_all_levels():
    """legend 模板应包含 A/B/C/D 四级完整定义（2026-07-25 起不再标注来源）。"""
    from processors.paper_report_generator import _get_template_env
    env = _get_template_env()
    tpl = env.get_template("markdown/legend.md.j2")
    rendered = tpl.module.legend()
    for level, short in [
        ("A", "直接相关"),
        ("B", "间接相关"),
        ("C", "同领域但距离远"),
        ("D", "不相关"),
    ]:
        assert f"**{level}**（{short}）" in rendered
    # 2026-07-25 起不再标注来源路径
    assert "relevance.yaml" not in rendered
    assert "Phase E LLM Prompt" not in rendered


def test_html_style_css_loaded_into_document():
    """HTML 完整文档的 <style> 块应包含 style.css 内的 body 选择器（证明 CSS 真的被加载）。"""
    from processors.paper_report_generator import _load_style_css
    css = _load_style_css()
    assert "body" in css
    assert "blockquote" in css  # 含图例样式
    # 实际嵌入到完整 HTML 后 <style> 标签内
    html = generate_report([_sample_paper()], format="html", full_html=True)
    assert "<style>" in html
    assert "blockquote.relevance-legend" in html
