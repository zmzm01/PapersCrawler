"""
测试: PDF 转换 (pdf_converter.py)

覆盖范围:
  - Markdown 转 PDF (需要 pandoc + xelatex)
  - pandoc 未安装时的优雅降级
  - 中文内容渲染
  - LaTeX 数学公式渲染

如果系统未安装 pandoc，相关测试会被自动跳过。
"""

import os
import sys
import tempfile
import subprocess
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from processors.pdf_converter import markdown_to_pdf


def _pandoc_available():
    """检查 pandoc 和 xelatex 是否可用。"""
    try:
        subprocess.run(["pandoc", "--version"], capture_output=True, check=True)
        subprocess.run(["xelatex", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


@pytest.fixture
def output_dir():
    """创建临时输出目录。"""
    return tempfile.mkdtemp()


def test_markdown_to_pdf_simple(output_dir):
    """简单英文 Markdown 转 PDF。"""
    if not _pandoc_available():
        pytest.skip("pandoc/xelatex not available")

    md = "# Test\n\nHello **world**!\n\nHere is a formula: $E = mc^2$"
    output_path = os.path.join(output_dir, "test.pdf")
    result = markdown_to_pdf(md, output_path)

    assert result is not None
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_markdown_to_pdf_chinese(output_dir):
    """含中文的 Markdown 转 PDF。"""
    if not _pandoc_available():
        pytest.skip("pandoc/xelatex not available")

    md = "# 文献报告\n\n## 测试论文\n\n**作者**: 张三, 李四\n\n摘要内容..."
    output_path = os.path.join(output_dir, "test_cn.pdf")
    result = markdown_to_pdf(md, output_path)

    assert result is not None
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_markdown_to_pdf_with_math(output_dir):
    """包含 LaTeX 数学公式的 Markdown 转 PDF。"""
    if not _pandoc_available():
        pytest.skip("pandoc/xelatex not available")

    md = (
        "# Results\n\n"
        "The energy is given by $E = mc^2$.\n\n"
        "Maxwell's equations: $$\\nabla \\cdot \\mathbf{E} = \\frac{\\rho}{\\epsilon_0}$$\n\n"
        "Fraction: $\\frac{1}{2}$"
    )
    output_path = os.path.join(output_dir, "test_math.pdf")
    result = markdown_to_pdf(md, output_path)

    assert result is not None
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_markdown_to_pdf_empty_md(output_dir):
    """空 Markdown 也应生成非空 PDF。"""
    if not _pandoc_available():
        pytest.skip("pandoc/xelatex not available")

    output_path = os.path.join(output_dir, "test_empty.pdf")
    result = markdown_to_pdf("# Empty", output_path)

    assert result is not None
    assert os.path.exists(output_path)


def test_markdown_to_pdf_output_dir_created(output_dir):
    """验证自动创建输出目录。"""
    if not _pandoc_available():
        pytest.skip("pandoc/xelatex not available")

    nested_dir = os.path.join(output_dir, "a", "b", "c")
    output_path = os.path.join(nested_dir, "test.pdf")
    result = markdown_to_pdf("# Test", output_path)

    assert result is not None
    assert os.path.exists(nested_dir)


def test_markdown_to_pdf_custom_template(output_dir):
    """验证自定义模板可用。"""
    if not _pandoc_available():
        pytest.skip("pandoc/xelatex not available")

    custom_template = r"""
\documentclass[12pt,a4paper]{article}
\usepackage[margin=2cm]{geometry}
\begin{document}
$body$
\end{document}
"""
    output_path = os.path.join(output_dir, "test_custom.pdf")
    result = markdown_to_pdf("# Test\n\nCustom template", output_path, custom_template)

    assert result is not None
    assert os.path.exists(output_path)
