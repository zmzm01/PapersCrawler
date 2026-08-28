"""Build the public JSON snapshot that accompanies a generated paper report."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common import clean_extracted_text
from processors.report_presentation import build_report_presentation
from processors.summary_schema import SUMMARY_SCHEMA_VERSION, normalize_summary

PUBLIC_REPORT_SCHEMA_VERSION = 2


def report_id(report_date: str) -> str:
    """Return the stable public identifier for a report date.

    Parameters
    ----------
    report_date : str
        Report date in ``YYYYMMDD`` form.

    Returns
    -------
    str
        Stable report identifier.
    """
    return f"papers-{report_date}"


def build_public_report(
    papers: list[dict[str, Any]],
    report_date: str,
    scope_definition: dict[str, dict[str, Any]] | None = None,
    presentation: dict[str, Any] | None = None,
    report_identifier: str | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a public-safe, versioned report payload.

    Parameters
    ----------
    papers : list of dict
        Paper records produced by Phase G.
    report_date : str
        Report date in ``YYYYMMDD`` form.
    scope_definition : dict, optional
        Configured subfield definitions used for display labels.
    presentation : dict, optional
        Precomputed shared presentation metadata.
    report_identifier : str, optional
        Explicit public ID. Defaults to the date-based ID used by automatic
        reports.
    scope : dict, optional
        Structured description of the report selection.

    Returns
    -------
    dict
        JSON-serializable public report payload.
    """
    ordered = sorted(
        papers,
        key=lambda paper: (
            {"A": 0, "B": 1}.get(paper.get("relevance_category"), 99),
            -(int((paper.get("date") or "").replace("-", "")[:8] or 0)),
        ),
    )
    presentation = presentation or build_report_presentation(scope_definition, ordered)
    labels = presentation.get("subfieldLabels", {})
    items = []
    for index, paper in enumerate(ordered, start=1):
        summary = normalize_summary(paper.get("summary", {
            "one_sentence": paper.get("one_sentence"),
            "motivation_and_goal": paper.get("motivation_and_goal"),
            "key_setup_and_method": paper.get("key_setup_and_method"),
            "main_results_and_physics": paper.get("main_results_and_physics"),
            "limitations": paper.get("limitations"),
            "take_home_message": paper.get("take_home_message"),
        }))
        items.append({
            "rank": index,
            "title": paper.get("title") or "",
            "doi": paper.get("doi") or "",
            "pageUrl": paper.get("page_url") or "",
            "pdfUrl": paper.get("pdf_url") or "",
            "journal": paper.get("journal") or "",
            "authors": paper.get("authors") or [],
            "publishedAt": paper.get("date") or "",
            "relevanceCategory": paper.get("relevance_category") or "",
            "subfields": paper.get("matched_subdomains") or [],
            "subfieldLabels": [labels.get(field, field) for field in paper.get("matched_subdomains") or []],
            "relevanceReason": paper.get("relevance_reason") or "",
            "relevanceBasis": paper.get("relevance_basis") or "",
            "abstract": clean_extracted_text(paper.get("abstract")) or "",
            "oneSentence": summary["one_sentence"],
            # ``summary`` is the canonical machine-readable analysis. Keep
            # the legacy ``sections`` projection for existing site consumers.
            "summary": summary,
            "sections": {
                "motivation": summary["motivation_and_goal"],
                "method": summary["key_setup_and_method"],
                "results": summary["main_results_and_physics"],
                "limitations": summary["limitations"],
                "takeaway": summary["take_home_message"],
            },
        })
    core = sum(item["relevanceCategory"] == "A" for item in items)
    watch = sum(item["relevanceCategory"] == "B" for item in items)
    return {
        "schemaVersion": PUBLIC_REPORT_SCHEMA_VERSION,
        "summarySchemaVersion": SUMMARY_SCHEMA_VERSION,
        "id": report_identifier or report_id(report_date),
        "source": "papers",
        "title": "文献报告",
        "publishedAt": f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}T00:00:00+00:00",
        "generatedAt": datetime.now(UTC).isoformat(),
        "summary": f"核心推荐（A）{core} 篇；邻近观察（B）{watch} 篇。",
        "tags": ["论文", "文献"],
        "scope": scope or {},
        "content": {
            "header": {key: value for key, value in presentation.items() if key != "subfieldLabels"},
            "papers": items,
        },
    }


def write_public_report(
    path: Path,
    papers: list[dict[str, Any]],
    report_date: str,
    scope_definition: dict[str, dict[str, Any]] | None = None,
    presentation: dict[str, Any] | None = None,
    report_identifier: str | None = None,
    scope: dict[str, Any] | None = None,
) -> Path:
    """Atomically write a public report payload to disk.

    Parameters
    ----------
    path : Path
        Destination sidecar path.
    papers : list of dict
        Paper records produced by Phase G.
    report_date : str
        Report date in ``YYYYMMDD`` form.
    scope_definition : dict, optional
        Configured subfield definitions used for display labels.
    presentation : dict, optional
        Precomputed shared presentation metadata.
    report_identifier : str, optional
        Explicit public ID. Defaults to the date-based ID used by automatic
        reports.
    scope : dict, optional
        Structured description of the report selection.

    Returns
    -------
    Path
        Written sidecar path.
    """
    payload = build_public_report(
        papers,
        report_date,
        scope_definition,
        presentation,
        report_identifier,
        scope,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
