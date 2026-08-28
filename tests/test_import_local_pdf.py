"""Regression tests for local PDF import persistence."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.database import DatabaseClient
import tools.import_local_pdf as import_local_pdf


def test_main_persists_pending_status_after_copying_pdf(tmp_path, monkeypatch, capsys):
    """Local import must commit the pending status, not only report rowcount."""
    database_path = tmp_path / "papers.db"
    output_dir = tmp_path / "mineru_output"
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"%PDF-1.7\nlocal test PDF")

    with DatabaseClient(database_path) as database:
        database.init_db_papers()
        database.conn.execute(
            "INSERT INTO papers (doi, mineru_parse_status, mineru_parse_error) "
            "VALUES (?, ?, ?)",
            ("10.1103/test-local-import", "failed", "old error"),
        )
        database.conn.commit()

    monkeypatch.setattr(import_local_pdf, "DB_PATH", database_path)
    monkeypatch.setattr(import_local_pdf, "MINERU_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_local_pdf.py",
            "--doi",
            "10.1103/test-local-import",
            "--pdf",
            str(source_pdf),
        ],
    )

    import_local_pdf.main()

    destination = output_dir / "10.1103_test-local-import" / "paper.pdf"
    assert destination.read_bytes() == source_pdf.read_bytes()
    assert "影响行数=1" in capsys.readouterr().out

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT mineru_parse_status, mineru_parse_error, mineru_parse_date "
            "FROM papers WHERE doi = ?",
            ("10.1103/test-local-import",),
        ).fetchone()

    assert row == ("pending", None, None)
