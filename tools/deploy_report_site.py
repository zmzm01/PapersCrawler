#!/usr/bin/env python3
"""Build and deploy the public Astro report site to Cloudflare Pages.

The site publishes automatic reports and the public legacy archive only. Group
special reports under ``data/reports/user`` are deliberately never exported.
Cloudflare API credentials and the Pages project are read from the repository's
local, gitignored ``.env`` file.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_SITE_DIR = PROJECT_ROOT / "report-site"
REPORT_DATA_DIR = REPORT_SITE_DIR / "src" / "data" / "reports"
AUTO_REPORT_DIR = PROJECT_ROOT / "data" / "reports" / "auto"
LEGACY_REPORT_DIR = PROJECT_ROOT / "data" / "reports" / "legacy"
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
    """Upload the built static site to a configured Cloudflare Pages project."""
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


def _load_deploy_credentials(environment: dict[str, str]) -> tuple[str, str, str]:
    """Load required Cloudflare deployment values from the environment.

    Parameters
    ----------
    environment : dict[str, str]
        Process environment, including values loaded from the project ``.env``.

    Returns
    -------
    tuple[str, str, str]
        Account ID, API token, and Pages project name.

    Raises
    ------
    RuntimeError
        If a required deployment value is missing.
    """
    values = {
        "CLOUDFLARE_ACCOUNT_ID": environment.get("CLOUDFLARE_ACCOUNT_ID"),
        "CLOUDFLARE_API_TOKEN": environment.get("CLOUDFLARE_API_TOKEN"),
        "CLOUDFLARE_PAGES_PROJECT": environment.get("CLOUDFLARE_PAGES_PROJECT"),
    }
    missing = [
        name for name, value in values.items() if not str(value or "").strip()
    ]
    if missing:
        raise RuntimeError(
            "Cloudflare Pages deployment values missing from .env: "
            + ", ".join(missing)
        )
    return (
        str(values["CLOUDFLARE_ACCOUNT_ID"]).strip(),
        str(values["CLOUDFLARE_API_TOKEN"]).strip(),
        str(values["CLOUDFLARE_PAGES_PROJECT"]).strip(),
    )


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
        "--branch",
        help="Upload as a Cloudflare preview branch instead of production.",
    )
    args = parser.parse_args()

    if not AUTO_REPORT_DIR.exists():
        raise SystemExit(f"Automatic report directory does not exist: {AUTO_REPORT_DIR}")
    if not REPORT_SITE_DIR.exists():
        raise SystemExit(f"Report site directory does not exist: {REPORT_SITE_DIR}")

    load_dotenv(PROJECT_ROOT / ".env")
    env = os.environ.copy()
    account_id, api_token, project_name = _load_deploy_credentials(env)
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    env["CLOUDFLARE_API_TOKEN"] = api_token

    sources = [AUTO_REPORT_DIR]
    if LEGACY_REPORT_DIR.exists():
        sources.append(LEGACY_REPORT_DIR)
    exported = export_reports(REPORT_DATA_DIR, sources, DB_PATH)
    print(f"Exported {exported} public report(s) to {REPORT_DATA_DIR}")

    node_bin = _resolve_node_bin()
    env["PATH"] = f"{node_bin}:{env.get('PATH', '')}"
    output_dir = _build_site(node_bin, args.install, env)
    _validate_output(output_dir)

    if args.dry_run:
        print(
            f"[DRY-RUN] Would deploy {output_dir} to Cloudflare Pages project "
            f"{project_name}"
        )
        return 0
    _deploy(output_dir, node_bin, project_name, args.branch, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
