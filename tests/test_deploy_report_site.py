"""Tests for the Cloudflare Pages report-site deployment wrapper."""

from pathlib import Path
from unittest.mock import patch

from tools import deploy_report_site


def test_deploy_passes_configured_pages_project(tmp_path):
    """Deployment passes the configured Pages project to Wrangler."""
    node_bin = tmp_path / "node-bin"
    node_bin.mkdir()
    output_dir = tmp_path / "dist"
    output_dir.mkdir()

    with patch("tools.deploy_report_site._run") as run:
        deploy_report_site._deploy(
            output_dir,
            node_bin,
            "paperscrawler-reports",
            "staging",
            {"PATH": ""},
        )

    command = run.call_args.args[0]
    assert command == [
        str(node_bin / "npx"),
        "wrangler",
        "pages",
        "deploy",
        str(output_dir),
        "--project-name",
        "paperscrawler-reports",
        "--branch",
        "staging",
    ]


def test_load_deploy_credentials_reads_environment_values():
    """The existing project environment supplies all Wrangler values."""
    values = deploy_report_site._load_deploy_credentials({
        "CLOUDFLARE_ACCOUNT_ID": "account-id",
        "CLOUDFLARE_API_TOKEN": "token-value",
        "CLOUDFLARE_PAGES_PROJECT": "site-name",
    })

    assert values == (
        "account-id",
        "token-value",
        "site-name",
    )


def test_load_deploy_credentials_names_missing_values():
    """A missing .env value produces an actionable deployment error."""
    try:
        deploy_report_site._load_deploy_credentials({
            "CLOUDFLARE_ACCOUNT_ID": "account-id",
        })
    except RuntimeError as error:
        assert str(error) == (
            "Cloudflare Pages deployment values missing from .env: "
            "CLOUDFLARE_API_TOKEN, CLOUDFLARE_PAGES_PROJECT"
        )
    else:
        raise AssertionError("Expected missing Cloudflare credentials to fail")


def test_main_injects_local_config_only_into_deploy_process(tmp_path, monkeypatch):
    """Main forwards local credentials to Wrangler without shell exports."""
    output_dir = tmp_path / "dist"
    output_dir.mkdir()
    node_bin = tmp_path / "node-bin"
    node_bin.mkdir()
    monkeypatch.setattr(deploy_report_site, "AUTO_REPORT_DIR", tmp_path)
    monkeypatch.setattr(deploy_report_site, "LEGACY_REPORT_DIR", tmp_path / "legacy")
    monkeypatch.setattr(deploy_report_site, "REPORT_SITE_DIR", tmp_path)
    monkeypatch.setattr(deploy_report_site, "REPORT_DATA_DIR", tmp_path / "reports")
    monkeypatch.setattr(deploy_report_site.sys, "argv", ["deploy_report_site.py"])
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-id")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-value")
    monkeypatch.setenv("CLOUDFLARE_PAGES_PROJECT", "site-name")

    with (
        patch("tools.deploy_report_site.export_reports", return_value=1) as export,
        patch("tools.deploy_report_site._resolve_node_bin", return_value=node_bin),
        patch("tools.deploy_report_site._build_site", return_value=output_dir) as build,
        patch("tools.deploy_report_site._validate_output"),
        patch("tools.deploy_report_site._deploy") as deploy,
    ):
        assert deploy_report_site.main() == 0

    build_environment = build.call_args.args[2]
    assert build_environment["CLOUDFLARE_ACCOUNT_ID"] == "account-id"
    assert build_environment["CLOUDFLARE_API_TOKEN"] == "token-value"
    assert deploy.call_args.args[2] == "site-name"
    assert export.call_args.args[1] == [tmp_path]
