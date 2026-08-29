#!/usr/bin/env python
"""Convert a Markdown report to PDF with static KaTeX HTML and Prince."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from processors.md_to_pdf_prince import markdown_to_pdf


def main() -> int:
    """Parse CLI arguments and convert one Markdown file."""
    parser = argparse.ArgumentParser(
        description="Render Markdown with static KaTeX HTML, then Prince PDF.",
    )
    parser.add_argument("input", type=Path, help="Input Markdown file")
    parser.add_argument("output", type=Path, nargs="?", help="Output PDF path")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"input file does not exist: {args.input}")
    output = args.output or args.input.with_suffix(".pdf")
    if markdown_to_pdf(args.input.read_text(encoding="utf-8"), output):
        print(f"PDF written: {output}")
        return 0
    print("PDF conversion failed; check Node.js, npm dependencies, and Prince.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
