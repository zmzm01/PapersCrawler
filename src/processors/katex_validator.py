"""Validate PapersCrawler formula delimiters with the shared KaTeX renderer."""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RENDERER_SCRIPT = PROJECT_ROOT / "report-site" / "scripts" / "render-markdown-katex.mjs"


def find_node() -> str | None:
    """Find Node.js from PATH or the user's nvm installation."""
    node_path = shutil.which("node")
    if node_path:
        return node_path
    nvm_dir = Path(os.environ.get("NVM_DIR", "/path/to/nvm"))
    candidates = sorted(nvm_dir.glob("versions/node/*/bin/node"))
    return str(candidates[-1]) if candidates else None


def validate_katex_formulas(text: str) -> list[dict] | None:
    """Return strict KaTeX errors in ``text``, or ``None`` if unavailable.

    A missing Node.js executable or renderer dependency is an optional-tooling
    condition, rather than a FormulaFixer failure. The caller can therefore
    retain the existing LLM-only behavior on minimal installations.

    Parameters
    ----------
    text : str
        Text containing ``\\(...\\)`` or ``\\[...\\]`` formula delimiters.

    Returns
    -------
    list[dict] | None
        Empty list for valid formulas, parsed error dictionaries for invalid
        formulas, or ``None`` when the local renderer cannot be run.
    """
    node_path = find_node()
    if r"\(" not in text and r"\[" not in text:
        return []
    if not RENDERER_SCRIPT.is_file() or not node_path:
        return None
    try:
        completed = subprocess.run(
            [node_path, str(RENDERER_SCRIPT), "--validate"],
            input=text,
            capture_output=True,
            check=True,
            encoding="utf-8",
            timeout=20,
        )
        result = json.loads(completed.stdout)
        return result.get("errors", [])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        logger.warning("KaTeX formula validation unavailable: %s", error)
        return None
