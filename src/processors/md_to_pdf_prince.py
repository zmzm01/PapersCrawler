"""Render Markdown through static KaTeX HTML and Prince XML."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from processors.katex_validator import find_node

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KATEX_RENDERER = PROJECT_ROOT / "report-site" / "scripts" / "render-markdown-katex.mjs"


def markdown_to_pdf(md_text: str, pdf_path: str | Path) -> bool:
    """Convert Markdown to PDF using static KaTeX HTML and Prince.

    The renderer never relies on a browser or external CDN at conversion time.
    Node.js renders Markdown and formulas into a temporary HTML directory whose
    KaTeX CSS and fonts are copied locally; Prince then performs pagination.

    Parameters
    ----------
    md_text : str
        Markdown with ``\\(...\\)`` and ``\\[...\\]`` formulas.
    pdf_path : str | Path
        Destination PDF path.

    Returns
    -------
    bool
        ``True`` only when both static HTML rendering and Prince succeed.
    """
    node_path = find_node()
    prince_path = shutil.which("prince")
    if not node_path or not prince_path:
        logger.warning("Markdown PDF requires both node and prince executables")
        return False
    if not KATEX_RENDERER.is_file():
        logger.warning("KaTeX renderer script not found: %s", KATEX_RENDERER)
        return False

    destination = Path(pdf_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="paperscrawler-prince-") as directory:
        work_dir = Path(directory)
        markdown_path = work_dir / "report.md"
        html_path = work_dir / "report.html"
        markdown_path.write_text(md_text, encoding="utf-8")
        try:
            subprocess.run(
                [node_path, str(KATEX_RENDERER), str(markdown_path), str(html_path)],
                capture_output=True,
                check=True,
                encoding="utf-8",
                timeout=60,
            )
            subprocess.run(
                [prince_path, str(html_path), "-o", str(destination)],
                capture_output=True,
                check=True,
                encoding="utf-8",
                timeout=120,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or str(error)).strip()
            logger.error("Prince Markdown PDF conversion failed: %s", detail)
            return False
        except (OSError, subprocess.SubprocessError) as error:
            logger.error("Prince Markdown PDF conversion failed: %s", error)
            return False
    return destination.is_file() and destination.stat().st_size > 0
