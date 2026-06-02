#!/usr/bin/env python
"""
将 Markdown 报告转换为 PDF。

流程:
  1. pandoc: Markdown → HTML（--mathml 模式，MathML 由浏览器原生渲染）
  2. cloakbrowser: 渲染 HTML → 打印 PDF

消除了 pandoc → xelatex 路径中 LaTeX 编译错误的脆弱性。

用法:
    python tools/convert_md_to_pdf.py data/reports/report_20260601.md

系统依赖:
    pip install cloakbrowser "cloakbrowser[geoip]"
    sudo apt install pandoc
"""

import sys
import subprocess
import tempfile
import time
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent))

from cloakbrowser import launch_persistent_context


def md_to_html(md_text: str) -> str:
    """用 pandoc 将 Markdown 转换为含 MathJax 的 HTML。"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(md_text)
        md_path = f.name

    html_path = md_path + ".html"
    try:
        subprocess.run(
            [
                "pandoc", md_path, "-o", html_path,
                "--mathml",
                "--standalone",
                "--from", "markdown+raw_tex+tex_math_dollars",
            ],
            check=True, capture_output=True, text=True,
        )
        html = Path(html_path).read_text(encoding="utf-8")
    except subprocess.CalledProcessError as e:
        print(f"pandoc 转换失败:\n{e.stderr[:500]}")
        sys.exit(1)
    except FileNotFoundError:
        print("pandoc 未安装，请先安装: sudo apt install pandoc")
        sys.exit(1)
    finally:
        Path(md_path).unlink(missing_ok=True)
        Path(html_path).unlink(missing_ok=True)

    return html


def html_to_pdf(html: str, pdf_path: str, timeout: int = 30) -> bool:
    """用 cloakbrowser 加载 HTML 并打印为 PDF。"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(html)
        html_path = f.name

    try:
        context = launch_persistent_context(
            user_data_dir=str(
                Path(tempfile.gettempdir()) / "paperscrawler_md2pdf"
            ),
            headless=True,
        )
        page = context.new_page()
        page.goto(f"file://{html_path}")
        # 等待 MathJax 渲染完成 + 额外缓冲
        try:
            page.wait_for_function(
                "typeof MathJax !== 'undefined' && "
                "MathJax.startup?.documentReady?.()",
                timeout=15000,
            )
        except Exception:
            # MathJax 未加载或已超时，等额外 5s 确保渲染
            time.sleep(5)

        page.pdf(
            path=pdf_path,
            margin={"top": "2cm", "bottom": "2cm",
                    "left": "2.5cm", "right": "2.5cm"},
        )
        return True
    except Exception as e:
        print(f"PDF 生成失败: {e}")
        return False
    finally:
        try:
            context.close()
        except Exception:
            pass
        Path(html_path).unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python {sys.argv[0]} <input.md>")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"文件不存在: {md_path}")
        sys.exit(1)

    pdf_path = md_path.with_suffix(".pdf")
    print(f"读取: {md_path}")

    md_text = md_path.read_text(encoding="utf-8")
    print("转换 Markdown → HTML ...")
    html = md_to_html(md_text)

    print("渲染 HTML → PDF (cloakbrowser) ...")
    if html_to_pdf(html, str(pdf_path)):
        print(f"PDF 已生成: {pdf_path}")
    else:
        print("PDF 生成失败")
        sys.exit(1)
