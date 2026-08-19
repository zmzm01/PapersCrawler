import json

from tools.export_public_reports import export_reports
from processors.public_report import build_public_report


def test_public_report_keeps_a_before_b_and_uses_public_fields():
    payload = build_public_report([
        {"title": "B paper", "date": "2026-08-20", "relevance_category": "B"},
        {"title": "A paper", "date": "2026-08-19", "relevance_category": "A", "doi": "10.1/a"},
    ], "20260820")

    assert payload["id"] == "papers-20260820"
    assert [paper["title"] for paper in payload["content"]["papers"]] == ["A paper", "B paper"]
    assert payload["content"]["papers"][0]["doi"] == "10.1/a"


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
