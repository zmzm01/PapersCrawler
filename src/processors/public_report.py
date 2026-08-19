"""Build the public JSON snapshot that accompanies a generated paper report."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from processors.report_presentation import build_report_presentation


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
            "abstract": paper.get("abstract") or "",
            "oneSentence": paper.get("one_sentence") or "",
            "sections": {
                "motivation": paper.get("motivation_and_goal") or "",
                "method": paper.get("key_setup_and_method") or "",
                "results": paper.get("main_results_and_physics") or "",
                "takeaway": paper.get("take_home_message") or "",
            },
        })
    core = sum(item["relevanceCategory"] == "A" for item in items)
    watch = sum(item["relevanceCategory"] == "B" for item in items)
    return {
        "schemaVersion": 1,
        "id": report_id(report_date),
        "source": "papers",
        "title": "文献报告",
        "publishedAt": f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}T00:00:00+00:00",
        "generatedAt": datetime.now(UTC).isoformat(),
        "summary": f"核心推荐（A）{core} 篇；邻近观察（B）{watch} 篇。",
        "tags": ["论文", "文献"],
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

    Returns
    -------
    Path
        Written sidecar path.
    """
    payload = build_public_report(papers, report_date, scope_definition, presentation)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
