#!/usr/bin/env python
"""
Convert Phase G reports to Hugo content and optionally deploy to GitHub Pages.

Usage:
  python tools/convert_reports_to_hugo.py                          # Latest auto report
  python tools/convert_reports_to_hugo.py --all                    # All reports
  python tools/convert_reports_to_hugo.py --report data/reports/auto/report_20260615.md
  python tools/convert_reports_to_hugo.py --all --hugo             # Convert + build
  python tools/convert_reports_to_hugo.py --all --hugo --deploy    # Convert + build + deploy
  python tools/convert_reports_to_hugo.py --dry-run                # Preview only
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

SITE_DIR = PROJECT_ROOT / "site"
CONTENT_DIR = SITE_DIR / "content" / "posts"
AUTO_REPORT_DIR = PROJECT_ROOT / "data" / "reports" / "auto"
USER_REPORT_DIR = PROJECT_ROOT / "data" / "reports" / "user"


def _ensure_ghp_import():
    """Install ghp-import via pip if not available."""
    if shutil.which("ghp-import"):
        return True
    try:
        import ghp_import  # noqa: F401
        return True
    except ImportError:
        pass
    print("Installing ghp-import...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "ghp-import"],
    )
    return True


def _extract_date(filename: str) -> str:
    """Extract ISO date from filename like report_20260615.md or report_20260615_143022.md."""
    m = re.search(r"report_(\d{4})(\d{2})(\d{2})(?:_(\d{2})(\d{2})(\d{2}))?", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _build_front_matter(title: str, date_str: str, source: str,
                         description: str = "", show_toc: bool = True) -> str:
    desc_line = f'description: "{description}"\n' if description else ""
    toc_line = "ShowToc: true\nTocOpen: true\n" if show_toc else ""
    return f"""---
title: "{title}"
date: {date_str}
source: "{source}"
{desc_line}{toc_line}---
"""


def _count_papers(content: str) -> int:
    """Count research papers in a report by counting ## headings excluding TOC."""
    headings = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
    # Exclude TOC / 目录 and "---" separator lines that might be captured
    return sum(1 for h in headings if h.strip() not in ("目录", "Table of Contents", "---"))


def _build_description(content: str, date_str: str) -> str:
    """Generate a short description for the report."""
    paper_count = _count_papers(content)
    date_display = date_str if date_str else "本期"
    return f"{date_display} — 共收录 {paper_count} 篇相关论文"


def convert_report(src_path: Path, dry_run: bool = False) -> Path | None:
    """Convert a single report file to Hugo content.

    Parameters
    ----------
    src_path : Path
        Path to the source report .md file.
    dry_run : bool
        If True, only print what would be done.

    Returns
    -------
    Path | None
        Output path if written, None if skipped.
    """
    stem = src_path.stem  # e.g. report_20260615
    content = src_path.read_text(encoding="utf-8")

    # Extract title from first # heading
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else f"报告 {stem}"

    date_str = _extract_date(stem)
    source = "auto" if "auto" in str(src_path) else "user"
    description = _build_description(content, date_str)

    fm = _build_front_matter(title, date_str, source, description=description)
    out_path = CONTENT_DIR / f"{stem}.md"

    if dry_run:
        print(f"[DRY-RUN] {src_path} → {out_path} ({len(content)} chars)")
        return None

    out_path.write_text(fm + content, encoding="utf-8")
    print(f"Written: {out_path} ({len(content)} chars)")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert Phase G reports to Hugo content and optionally deploy",
    )
    parser.add_argument(
        "--report", type=str, default=None,
        help="Convert a specific report file (path or filename stem)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Convert all auto-generated reports from auto/ directory",
    )
    parser.add_argument(
        "--hugo", action="store_true",
        help="Run `hugo` build after conversion",
    )
    parser.add_argument(
        "--deploy", action="store_true",
        help="Deploy to GitHub Pages gh-pages branch via ghp-import",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview conversion without writing files",
    )
    args = parser.parse_args()

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    # Collect source files
    sources = []

    if args.report:
        rp = Path(args.report)
        if rp.exists():
            sources.append(rp)
        else:
            # Try auto/ and user/ with stem matching
            for d in [AUTO_REPORT_DIR, USER_REPORT_DIR]:
                candidate = d / f"{rp}.md"
                if not rp.suffix:
                    candidate = d / f"{args.report}.md"
                if candidate.exists():
                    sources.append(candidate)
                    break
            if not sources:
                print(f"Report not found: {args.report}")
                sys.exit(1)
    elif args.all:
        if AUTO_REPORT_DIR.exists():
            sources.extend(sorted(AUTO_REPORT_DIR.glob("report_*.md")))
        if not sources:
            print("No auto reports found.")
            return
    else:
        # Default: latest auto report
        if AUTO_REPORT_DIR.exists():
            reports = sorted(AUTO_REPORT_DIR.glob("report_*.md"))
            if reports:
                sources.append(reports[-1])
        if not sources:
            print("No auto reports found. Use --report or --all to specify.")
            return

    # Clean old content and convert
    if args.all and not args.dry_run:
        for old in CONTENT_DIR.glob("report_*.md"):
            old.unlink()

    converted = 0
    for src in sources:
        out = convert_report(src, dry_run=args.dry_run)
        if out:
            converted += 1

    if args.dry_run:
        print(f"\n[DRY-RUN] Would convert {len(sources)} report(s)")
        return

    print(f"Converted {converted} report(s) to {CONTENT_DIR}")

    # Hugo build
    if args.hugo:
        print("Running hugo build...")
        result = subprocess.run(
            ["hugo"], cwd=SITE_DIR, capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"Hugo build successful: {SITE_DIR / 'public'}")
        else:
            print(f"Hugo build failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)

    # Deploy to GitHub Pages
    if args.deploy:
        _ensure_ghp_import()
        public_dir = SITE_DIR / "public"
        if not public_dir.exists():
            print("No public/ directory — run with --hugo first or build manually.")
            sys.exit(1)
        print("Deploying to gh-pages branch via ghp-import...")
        subprocess.check_call([
            "ghp-import", "-r", "public", "-p", "-f", str(public_dir),
        ])
        print("Deployed: https://zmzm01.github.io/PapersCrawler/")


if __name__ == "__main__":
    main()
