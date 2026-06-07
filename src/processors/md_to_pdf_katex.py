"""
md_to_pdf_katex.py
==================
将含有 \\(...\\) / \\[...\\] LaTeX 公式的 Markdown 渲染为 PDF。

使用与 WebUI 报告页面相同的渲染链路：
  Markdown -> marked.js -> HTML -> KaTeX 公式渲染 -> cloakbrowser 打印 PDF

不依赖 pandoc / texlive / xelatex。
"""

import json
import logging
import tempfile
from pathlib import Path

from cloakbrowser import launch_persistent_context

logger = logging.getLogger(__name__)

KATEX_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/marked@15.0.8/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<style>
  @page { margin: 1.5cm; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 12pt;
    line-height: 1.7;
    color: #1e293b;
    max-width: 800px;
    margin: 0 auto;
    padding: 0;
  }
  h1 { font-size: 1.4rem; margin: 1.2rem 0 0.6rem; }
  h2 { font-size: 1.2rem; margin: 1.2rem 0 0.5rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.25rem; }
  h3 { font-size: 1.05rem; margin: 0.8rem 0 0.3rem; }
  p { margin: 0.5rem 0; }
  strong { font-weight: 600; }
  ul, ol { margin: 0.5rem 0; padding-left: 1.5rem; }
  code { background: #f1f5f9; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.85rem; }
  .katex { font-size: 1.05em; }
  .katex-error { color: #cc0000; font-size: 0.85rem; }
  .error-fallback { color: #ef4444; border: 1px solid #fecaca; background: #fef2f2; padding: 1rem; border-radius: 6px; white-space: pre-wrap; }
</style>
</head>
<body>
<div id="content"></div>
<script>
var markdown = {md_json};

function renderReport() {
  try {
    if (typeof marked === 'undefined') {
      document.getElementById('content').innerHTML = '<div class="error-fallback">Error: marked.js not loaded</div>';
      return;
    }
    var placeholders = {};
    var pid = 0;
    var protected_md = markdown.replace(
      /\\([\s\S]*?\\)|\\\[[\s\S]*?\\\]/g,
      function(m) { var k = '@@KX' + (pid++) + '@@'; placeholders[k] = m; return k; }
    );
    var html = marked.parse(protected_md, { breaks: true, gfm: true });
    for (var k in placeholders) {
      html = html.split(k).join(placeholders[k]);
    }
    document.getElementById('content').innerHTML = html;
    if (typeof renderMathInElement !== 'undefined') {
      renderMathInElement(document.getElementById('content'), {
        delimiters: [
          {left: '\\[', right: '\\]', display: true},
          {left: '\\(', right: '\\)', display: false},
        ],
        throwOnError: false,
        errorColor: '#cc0000',
      });
    }
  } catch (e) {
    document.getElementById('content').innerHTML = '<div class="error-fallback">Render error: ' + e.message + '</div>';
  }
}

renderReport();
</script>
</body>
</html>"""


def md_to_pdf(md_text: str, pdf_path: str) -> bool:
    """将含 LaTeX 公式的 Markdown 渲染为 PDF。

    使用 marked.js + KaTeX（与 WebUI 报告页一致）进行渲染，
    然后由 cloakbrowser 无头打印为 PDF。

    Parameters
    ----------
    md_text : str
        Markdown 文本，支持 \\(...\\) 行内公式和 \\[...\\] 独立公式。
    pdf_path : str
        输出的 PDF 文件路径。

    Returns
    -------
    bool
        成功返回 True，失败返回 False。
    """
    md_json = json.dumps(md_text)
    html = KATEX_HTML_TEMPLATE.replace("{md_json}", md_json)

    pdf_path = str(Path(pdf_path).resolve())
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(html)
        html_path = f.name

    try:
        context = launch_persistent_context(
            user_data_dir=str(
                Path(tempfile.gettempdir()) / "paperscrawler_md2pdf_katex"
            ),
            headless=True,
        )
        page = context.new_page()
        page.goto(f"file://{html_path}")

        try:
            page.wait_for_function(
                "typeof marked !== 'undefined' && typeof renderMathInElement !== 'undefined'",
                timeout=20000,
            )
        except Exception:
            logger.warning("CDN libraries not loaded, PDF may be blank")

        try:
            page.wait_for_function(
                "document.getElementById('content').textContent.trim().length > 0",
                timeout=15000,
            )
        except Exception:
            logger.warning("Content appears empty, continuing anyway")

        page.pdf(
            path=pdf_path,
            margin={"top": "1.5cm", "bottom": "1.5cm",
                    "left": "1.5cm", "right": "1.5cm"},
            print_background=True,
        )
        logger.info(f"PDF saved: {pdf_path}")
        return True

    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return False

    finally:
        Path(html_path).unlink(missing_ok=True)
        try:
            context.close()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <input.md> [output.pdf]")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"File not found: {md_path}")
        sys.exit(1)

    pdf_path = sys.argv[2] if len(sys.argv) > 2 else str(md_path.with_suffix(".pdf"))
    md_text = md_path.read_text(encoding="utf-8")

    print(f"Rendering {md_path.name} -> {Path(pdf_path).name} ...")
    if md_to_pdf(md_text, pdf_path):
        print(f"OK: {pdf_path}")
    else:
        print("FAILED")
        sys.exit(1)
