import json

from tools.export_public_reports import export_reports
from processors.public_report import (
    PUBLIC_REPORT_SCHEMA_VERSION,
    build_public_report,
)
from processors.summary_schema import SUMMARY_SCHEMA_VERSION


def test_public_report_keeps_a_before_b_and_uses_public_fields():
    payload = build_public_report([
        {"title": "B paper", "date": "2026-08-20", "relevance_category": "B"},
        {"title": "A paper", "date": "2026-08-19", "relevance_category": "A", "doi": "10.1/a"},
    ], "20260820")

    assert payload["id"] == "papers-20260820"
    assert [paper["title"] for paper in payload["content"]["papers"]] == ["A paper", "B paper"]
    assert payload["content"]["papers"][0]["doi"] == "10.1/a"


def test_public_report_separates_envelope_and_summary_versions():
    """The report envelope and paper-analysis schemas evolve independently."""
    payload = build_public_report([{
        "title": "Structured paper",
        "date": "2026-08-20",
        "limitations": [{
            "key": "sample_scope",
            "limitation": "样本范围有限",
            "impact": "外推性受限",
            "basis": "explicit",
        }],
    }], "20260820")

    paper = payload["content"]["papers"][0]
    assert payload["schemaVersion"] == PUBLIC_REPORT_SCHEMA_VERSION
    assert payload["summarySchemaVersion"] == SUMMARY_SCHEMA_VERSION
    assert paper["summary"]["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert paper["summary"]["limitations"][0]["key"] == "sample_scope"
    assert paper["sections"]["limitations"] == paper["summary"]["limitations"]


def test_public_report_supports_scope_and_preview_identifier():
    """Historical previews carry selection metadata and unique IDs."""
    payload = build_public_report(
        [],
        "20260821",
        report_identifier="papers-report-before-20260817",
        scope={
            "kind": "all",
            "beforeCreatedDate": "2026-08-17",
        },
    )

    assert payload["id"] == "papers-report-before-20260817"
    assert payload["scope"]["beforeCreatedDate"] == "2026-08-17"


def test_export_removes_stale_report_files_without_touching_other_files(tmp_path):
    """Export synchronization removes only report files it owns."""
    source_dir = tmp_path / "source"
    output_root = tmp_path / "output"
    source_dir.mkdir()
    destination = output_root / "papers"
    destination.mkdir(parents=True)
    (destination / "papers-old.json").write_text("{}", encoding="utf-8")
    (destination / "other-data.json").write_text("{}", encoding="utf-8")
    payload = build_public_report([], "20260820")
    (source_dir / "report_20260820.public.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    assert export_reports(output_root, source_dir, tmp_path / "missing.db") == 1
    assert not (destination / "papers-old.json").exists()
    assert (destination / "papers-20260820.json").exists()
    assert (destination / "other-data.json").exists()
    assert json.loads((destination / "index.json").read_text(encoding="utf-8"))[0]["id"] == "papers-20260820"


def test_export_merges_multiple_sources(tmp_path):
    """Automatic and explicitly published preview sidecars coexist."""
    automatic_dir = tmp_path / "automatic"
    preview_dir = tmp_path / "preview"
    output_root = tmp_path / "output"
    automatic_dir.mkdir()
    preview_dir.mkdir()

    automatic = build_public_report([], "20260820")
    preview = build_public_report([], "20260821", report_identifier="papers-history")
    (automatic_dir / "report_20260820.public.json").write_text(
        json.dumps(automatic), encoding="utf-8"
    )
    (preview_dir / "report_history.public.json").write_text(
        json.dumps(preview), encoding="utf-8"
    )

    assert export_reports(
        output_root,
        [automatic_dir, preview_dir],
        tmp_path / "missing.db",
    ) == 2
    assert (output_root / "papers" / "papers-20260820.json").exists()
    assert (output_root / "papers" / "papers-history.json").exists()
