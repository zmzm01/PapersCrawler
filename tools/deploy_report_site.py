#!/usr/bin/env python3
"""Build and optionally deploy the independent Astro report site.

The legacy Hugo site remains available through ``tools/convert_reports_to_hugo.py``.
This command publishes only the Astro site under ``report-site/`` and never
touches the ``gh-pages`` branch.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_SITE_DIR = PROJECT_ROOT / "report-site"
REPORT_DATA_DIR = REPORT_SITE_DIR / "src" / "data" / "reports"
AUTO_REPORT_DIR = PROJECT_ROOT / "data" / "reports" / "auto"
USER_REPORT_DIR = PROJECT_ROOT / "data" / "reports" / "user"
DB_PATH = PROJECT_ROOT / "data" / "papers.db"
FORBIDDEN_OUTPUT_MARKERS = (
    "CLOUDFLARE_API_TOKEN",
    "DEEPSEEK_API_KEY",
    "LLM_API_KEY",
    "MINERU_TOKEN",
    "report_explained",
    "full.md",
    "/path/to/Applications/",
)

sys.path.insert(0, str(PROJECT_ROOT))
from tools.export_public_reports import export_reports  # noqa: E402


def _resolve_node_bin() -> Path:
    """Resolve the active Node.js bin directory through nvm or PATH.

    Returns
    -------
    pathlib.Path
        Directory containing ``node``, ``npm`` and ``npx``.

    Raises
    ------
    RuntimeError
        If neither the configured nvm installation nor PATH provides Node.js.
    """
    nvm_dir = Path(os.environ.get("NVM_DIR", "/path/to/nvm"))
    nvm_script = nvm_dir / "nvm.sh"
    if nvm_script.exists():
        command = (
            f". {shlex.quote(str(nvm_script))} && "
            "nvm which default"
        )
        result = subprocess.run(
            ["bash", "-lc", command],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            node_path = Path(result.stdout.strip())
            if node_path.exists():
                return node_path.parent

    node_path = shutil.which("node")
    if node_path:
        return Path(node_path).resolve().parent
    raise RuntimeError(
        "Node.js not found. Set NVM_DIR or install Node.js before building "
        "the report site."
    )


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    """Run a visible subprocess and fail on a non-zero exit code."""
    print(f"$ {shlex.join(command)}")
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _build_site(node_bin: Path, install: bool, env: dict[str, str]) -> Path:
    """Install dependencies when requested and build the Astro site."""
    npm = node_bin / "npm"
    node_modules = REPORT_SITE_DIR / "node_modules"
    if install or not node_modules.exists():
        _run([str(npm), "ci"], REPORT_SITE_DIR, env)
    _run([str(npm), "run", "build"], REPORT_SITE_DIR, env)
    output_dir = REPORT_SITE_DIR / "dist"
    if not output_dir.is_dir():
        raise RuntimeError(f"Astro build did not create {output_dir}")
    return output_dir


def _deploy(
    output_dir: Path,
    node_bin: Path,
    project_name: str,
    branch: str | None,
    env: dict[str, str],
) -> None:
    """Upload the built static site to Cloudflare Pages."""
    npx = node_bin / "npx"
    command = [
        str(npx),
        "wrangler",
        "pages",
        "deploy",
        str(output_dir),
        "--project-name",
        project_name,
    ]
    if branch:
        command.extend(["--branch", branch])
    _run(command, REPORT_SITE_DIR, env)


def _validate_output(output_dir: Path) -> None:
    """Reject obvious credentials, local paths, and internal report pages."""
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in FORBIDDEN_OUTPUT_MARKERS:
            if marker in content:
                raise RuntimeError(f"Forbidden release marker {marker!r} found in {path}")


def main() -> int:
    """Parse arguments, export reports, build Astro, and deploy if requested."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Export and build, but do not upload to Cloudflare Pages.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Run npm ci before building, even when node_modules exists.",
    )
    parser.add_argument(
        "--include-user-reports",
        action="store_true",
        help="Also export explicitly generated user reports.",
    )
    parser.add_argument(
        "--branch",
        help="Upload as a Cloudflare preview branch instead of production.",
    )
    args = parser.parse_args()

    if not AUTO_REPORT_DIR.exists():
        raise SystemExit(f"Automatic report directory does not exist: {AUTO_REPORT_DIR}")
    if not REPORT_SITE_DIR.exists():
        raise SystemExit(f"Report site directory does not exist: {REPORT_SITE_DIR}")

    sources = [AUTO_REPORT_DIR]
    if args.include_user_reports:
        sources.append(USER_REPORT_DIR)
    exported = export_reports(REPORT_DATA_DIR, sources, DB_PATH)
    print(f"Exported {exported} public report(s) to {REPORT_DATA_DIR}")

    node_bin = _resolve_node_bin()
    env = os.environ.copy()
    env["PATH"] = f"{node_bin}:{env.get('PATH', '')}"
    output_dir = _build_site(node_bin, args.install, env)
    _validate_output(output_dir)

    project_name = os.environ.get("CLOUDFLARE_PAGES_PROJECT", "")
    if args.dry_run:
        print(
            "[DRY-RUN] Would deploy "
            f"{output_dir} to Cloudflare Pages project "
            f"{project_name or '<unset>'}"
        )
        return 0
    if not project_name:
        raise SystemExit("CLOUDFLARE_PAGES_PROJECT is required for deployment")
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        raise SystemExit("CLOUDFLARE_API_TOKEN is required for unattended deployment")
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        raise SystemExit("CLOUDFLARE_ACCOUNT_ID is required for unattended deployment")
    _deploy(output_dir, node_bin, project_name, args.branch, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
