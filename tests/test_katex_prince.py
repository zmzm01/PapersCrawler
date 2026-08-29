"""Unit and integration-light tests for the static KaTeX/Prince PDF path."""

import json
from pathlib import Path
import subprocess

import pytest

import processors.katex_validator as katex_validator
import processors.md_to_pdf_prince as prince_converter


def test_katex_validator_returns_renderer_errors(monkeypatch):
    """Renderer JSON diagnostics are made available to FormulaFixer."""
    completed = type(
        "Completed", (),
        {"stdout": json.dumps({"valid": False, "errors": [{"message": "bad"}]})},
    )()
    monkeypatch.setattr(katex_validator, "find_node", lambda: "/bin/node")
    monkeypatch.setattr(katex_validator.subprocess, "run", lambda *args, **kwargs: completed)

    assert katex_validator.validate_katex_formulas(r"\\(\\unknowncommand\\)") == [
        {"message": "bad"},
    ]


def test_katex_validator_is_optional_without_node(monkeypatch):
    """Minimal installations retain FormulaFixer's LLM-only behavior."""
    monkeypatch.setattr(katex_validator, "find_node", lambda: None)
    assert katex_validator.validate_katex_formulas(r"\\(x^2\\)") is None


def test_static_renderer_writes_html_and_local_katex_assets(tmp_path):
    """The real Node renderer produces offline HTML when its dependencies exist."""
    node_path = katex_validator.find_node()
    if not node_path:
        pytest.skip("Node.js unavailable")
    source = tmp_path / "report.md"
    output = tmp_path / "report.html"
    source.write_text("# Report\n\nInline \\(E=mc^2\\).", encoding="utf-8")
    try:
        subprocess.run(
            [node_path, str(katex_validator.RENDERER_SCRIPT), str(source), str(output)],
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as error:
        pytest.skip(f"KaTeX npm dependencies unavailable: {error.stderr}")
    assert "katex" in output.read_text(encoding="utf-8")
    assert (tmp_path / "katex-assets" / "katex.min.css").is_file()


def test_prince_converter_runs_static_renderer_then_prince(monkeypatch, tmp_path):
    """Prince receives the HTML written by the local Node renderer."""
    commands = []

    monkeypatch.setattr(prince_converter, "find_node", lambda: "/usr/bin/node")
    monkeypatch.setattr(prince_converter.shutil, "which", lambda name: "/usr/bin/prince")

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "/usr/bin/prince":
            Path(command[-1]).write_bytes(b"%PDF-1.7 test")
        return type("Completed", (), {"stdout": "", "stderr": ""})()

    monkeypatch.setattr(prince_converter.subprocess, "run", fake_run)
    output = tmp_path / "nested" / "report.pdf"

    assert prince_converter.markdown_to_pdf(r"# Report\\n\\n\\(E=mc^2\\)", output)
    assert commands[0][0] == "/usr/bin/node"
    assert commands[1][0] == "/usr/bin/prince"
    assert output.read_bytes().startswith(b"%PDF-")


def test_prince_converter_requires_local_tools(monkeypatch, tmp_path):
    """Missing Prince or Node fails safely without creating output."""
    monkeypatch.setattr(prince_converter, "find_node", lambda: None)
    assert not prince_converter.markdown_to_pdf("# Report", tmp_path / "report.pdf")
