"""
将 Markdown 报告转换为 PDF。

用法:
    python tools/convert_md_to_pdf.py data/reports/report_20260601.md

依赖（系统安装）:
    sudo apt install pandoc texlive-xetex texlive-latex-extra fonts-noto-cjk
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.pdf_converter import markdown_to_pdf


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python tools/convert_md_to_pdf.py <input.md>")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"文件不存在: {md_path}")
        sys.exit(1)

    pdf_path = md_path.with_suffix(".pdf")
    result = markdown_to_pdf(md_path.read_text(encoding="utf-8"), pdf_path)
    if result:
        print(f"PDF 已生成: {result}")
    else:
        print("PDF 生成失败，请检查 pandoc/xelatex 是否已安装")
        sys.exit(1)
