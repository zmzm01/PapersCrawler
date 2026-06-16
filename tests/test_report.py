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
    assert labels.get("advanced_technology") == "加速器控制与AI"


def test_build_subdomain_labels_empty():
    """空 scope_definition 返回空字典。"""
    assert _build_subdomain_labels({}) == {}


def test_build_subdomain_labels_fallback_key():
    """无法识别的描述应返回原始 key 作为标签。"""
    labels = _build_subdomain_labels({"custom": {"description": "一些自定义研究内容"}})
    assert labels.get("custom") == "custom"


# ---- scope_definition 标签在报告元数据中的显示 ----

def test_report_shows_subdomain_labels():
    """传入 scope_definition 时，匹配子领域应显示中文短标签。"""
    papers = [
        _sample_paper(matched_subdomains=["acceleration"], title="Paper A"),
    ]
    md = generate_report(papers, format="markdown", toc=True,
                         scope_definition=_SCOPE_DEF_FOR_LABELS)
    # 应显示中文短标签而非原始 key
    assert "加速与后加速" in md
    assert "acceleration" not in md
    # 依旧是平铺模式（## 标题）
    assert "## Paper A" in md


def test_report_shows_subdomain_labels_multi():
    """多子领域时显示所有标签。"""
    papers = [
        _sample_paper(
            matched_subdomains=["acceleration", "plasma_physics"],
            title="Paper A",
        ),
    ]
    md = generate_report(papers, format="markdown", toc=True,
                         scope_definition=_SCOPE_DEF_FOR_LABELS)
    assert "加速与后加速" in md
    assert "等离子体物理与诊断" in md


def test_report_no_scope_definition():
    """不传 scope_definition 时，子领域显示原始 key（兼容行为）。"""
    md = generate_report([_sample_paper(matched_subdomains=["acceleration"])],
                         format="markdown", toc=True)
    assert "加速与后加速" not in md
    assert "acceleration" in md


def test_report_empty_subdomain_labels_no_error():
    """matched_subdomains 为空时不应出现相关方向行。"""
    md = generate_report([_sample_paper(matched_subdomains=[])],
                         format="markdown", toc=True,
                         scope_definition=_SCOPE_DEF_FOR_LABELS)
    assert "相关方向" not in md


# ---- 异常 ----

def test_generate_report_invalid_format():
    """不支持的格式应抛出 ValueError。"""
    import pytest
    with pytest.raises(ValueError):
        generate_report([_sample_paper()], format="docx")
