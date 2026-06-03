"""
PapersCrawler Web UI — FastAPI application.

Provides a web interface for pipeline control, report generation,
log viewing, and configuration browsing.

Usage:
    PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080

    # On headless server (Phase C needs display):
    xvfb-run -a bash -c 'PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080'
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure src/ is importable
_src_path = Path(__file__).resolve().parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    DB_PATH, REPORT_DIR, LOG_FILE_PATH, DATA_DIR, CONFIG_DIR,
    load_publishers, load_keywords,
    SKIP_PHASE_A, SKIP_PHASE_B, SKIP_PHASE_C, SKIP_PHASE_D,
    SKIP_PHASE_E, SKIP_PHASE_E2, SKIP_PHASE_F, SKIP_PHASE_G, SKIP_PHASE_H,
)
from db.database import DatabaseClient
from pipeline.runner import _load_skip_overrides

app = FastAPI(title="PapersCrawler")

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

_running_phase: Optional[str] = None
_phase_lock = asyncio.Lock()

PHASE_LABELS = {
    "A": "RSS Fetch", "B": "CrossRef Metadata", "C": "Publisher Page",
    "D": "Semantic Filter", "E": "LLM Relevance", "E2": "MinerU PDF",
    "F": "LLM Summary", "G": "Report", "H": "Email",
}

PHASE_DEFAULTS = {
    "A": SKIP_PHASE_A, "B": SKIP_PHASE_B, "C": SKIP_PHASE_C,
    "D": SKIP_PHASE_D, "E": SKIP_PHASE_E, "E2": SKIP_PHASE_E2,
    "F": SKIP_PHASE_F, "G": SKIP_PHASE_G, "H": SKIP_PHASE_H,
}

SKIP_OVERRIDES_PATH = DATA_DIR / "skip_overrides.json"


def _get_effective_skip():
    overrides = _load_skip_overrides()
    return {k: overrides.get(k, PHASE_DEFAULTS[k]) for k in PHASE_DEFAULTS}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pipeline_status():
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    papers = db.get_all_papers()
    total = len(papers)
    cols = [
        ("cr_metadata_fetched", "cr_metadata_fetched_status"),
        ("publisher_page", "publisher_page_fetched_status"),
        ("semantic_filter", "semantic_filter_status"),
        ("llm_relevance", "llm_relevance_status"),
        ("mineru_parse", "mineru_parse_status"),
        ("llm_summary", "llm_summary_status"),
    ]
    phases = {}
    for label, col in cols:
        counts = {"success": 0, "failed": 0, "skipped": 0, "pending": 0}
        for p in papers:
            status = p[col] if p[col] else "pending"
            counts[status] = counts.get(status, 0) + 1
        phases[label] = counts
    return {"total": total, "phases": phases}


# Reset definitions: (columns_to_pending, cascade_info, extra_where)
RESET_DEFS = {
    "B": (["cr_metadata_fetched_status"], "cr_metadata_fetched_status != 'pending'", None),
    "C": (["publisher_page_fetched_status", "publisher_page_fetched_error"],
          "publisher_page_fetched_status IN ('failed','skipped') "
          "AND (publisher_page_fetched_error IS NULL "
          "OR publisher_page_fetched_error NOT LIKE 'NonResearchPageError:%')",
          None),
    "D": (["semantic_filter_status", "semantic_filter_error",
           "llm_relevance_status", "llm_relevance_result"],
          "semantic_filter_status IN ('success','failed','skipped')", None),
    "E": (["llm_relevance_status", "llm_relevance_result", "llm_relevance_confidence",
           "llm_relevance_reason", "llm_relevance_error"],
          "llm_relevance_status IN ('success','failed','skipped')", None),
    "E2": (["mineru_parse_status", "mineru_parse_error", "mineru_fulltext",
            "mineru_output_dir",
            "llm_summary_status", "llm_summary_result", "llm_summary_error"],
           "mineru_parse_status IN ('success','failed','skipped')", None),
    "F": (["llm_summary_status", "llm_summary_result", "llm_summary_error"],
           "llm_summary_status IN ('success','failed','skipped')", None),
    "G": (["report_status", "report_date"],
           "report_status = 'reported'", None),
}

RESET_CASCADE = {
    "B": "", "C": "", "D": "llm_relevance_status",
    "E": "", "E2": "llm_summary_status, report_status",
    "F": "report_status", "G": "",
}


def _run_phase_subprocess(phase, is_all=False):
    global _running_phase
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"

    def _run():
        global _running_phase
        try:
            if is_all:
                code = ("from pipeline.runner import run_pipeline; run_pipeline(force=True)")
            else:
                code = (f"from pipeline.runner import run_phases; run_phases({[phase]!r}, force=True)")
            subprocess.run(
                [sys.executable, "-c", f"import sys; sys.path.insert(0, '{src_dir}'); {code}"],
                cwd=project_root, capture_output=True, timeout=14400 if is_all else 3600,
            )
        except subprocess.TimeoutExpired:
            pass
        finally:
            _running_phase = None

    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ── Home ───────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    publishers = load_publishers()
    p_count = len(publishers)
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    total = len(db.get_all_papers())
    return templates.TemplateResponse(
        request, "home.html", {"publisher_count": p_count, "paper_count": total}
    )


# ── Pipeline ───────────────────────────────────────────────────────────────────

@app.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request):
    phases = [
        {"key": k, "label": PHASE_LABELS[k]}
        for k in PHASE_LABELS
    ]
    return templates.TemplateResponse(request, "pipeline.html", {"phases": phases})


@app.get("/pipeline/status")
async def pipeline_status_api():
    return JSONResponse(_pipeline_status())


@app.post("/pipeline/run/{phase}")
async def run_phase(phase: str):
    global _running_phase
    if phase not in PHASE_LABELS:
        return JSONResponse({"error": f"Unknown phase: {phase}"}, status_code=400)
    async with _phase_lock:
        if _running_phase:
            return JSONResponse({"error": f"Phase {_running_phase} is already running"}, status_code=409)
        _running_phase = phase
    _run_phase_subprocess(phase)
    return JSONResponse({"ok": True, "phase": phase})


@app.post("/pipeline/run-all")
async def run_all():
    global _running_phase
    async with _phase_lock:
        if _running_phase:
            return JSONResponse({"error": f"Phase {_running_phase} is already running"}, status_code=409)
        _running_phase = "ALL"
    _run_phase_subprocess(None, is_all=True)
    return JSONResponse({"ok": True, "phase": "ALL"})


@app.post("/pipeline/reset/{phase}")
async def reset_phase(phase: str):
    if phase not in RESET_DEFS:
        return JSONResponse({"error": f"Unsupported reset phase: {phase}"}, status_code=400)

    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    cols, reset_where, _ = RESET_DEFS[phase]
    col_names = [c for i, c in enumerate(cols) if i % 2 == 0]  # status columns only
    reset_cols = list(dict.fromkeys(col_names))  # unique, preserve order

    # Count impact
    impact = {}
    for c in reset_cols:
        cur = db.conn.execute(
            f"SELECT COUNT(*) FROM papers WHERE {c} IN ('success','failed','skipped')"
        )
        impact[c] = cur.fetchone()[0]

    # Execute reset
    for c in reset_cols:
        db.batch_reset_status([(c, "pending")], f"{c} IN ('success','failed','skipped')")

    return JSONResponse({"ok": True, "phase": phase, "impact": impact})


async def _log_event_stream():
    log_path = Path(LOG_FILE_PATH)
    last_size = log_path.stat().st_size if log_path.exists() else 0
    while True:
        if log_path.exists():
            current_size = log_path.stat().st_size
            if current_size > last_size:
                with open(log_path, "r", encoding="utf-8") as f:
                    f.seek(last_size)
                    new_lines = f.read()
                    if new_lines:
                        yield f"data: {json.dumps({'text': new_lines})}\n\n"
                last_size = current_size
        await asyncio.sleep(1)


@app.get("/pipeline/logs")
async def pipeline_logs_sse():
    return StreamingResponse(
        _log_event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── Papers ─────────────────────────────────────────────────────────────────────

@app.get("/papers", response_class=HTMLResponse)
async def papers_page(request: Request):
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    papers = db.get_papers_sorted_by_semantic(limit=100)
    return templates.TemplateResponse(request, "papers.html", {"papers": papers})


# ── Report ─────────────────────────────────────────────────────────────────────

@app.get("/report", response_class=HTMLResponse)
async def report_page(request: Request):
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    papers = db.get_papers_with_summaries()
    publishers = load_publishers()
    publisher_names = sorted(set(p["publisher"] for p in publishers if p.get("enabled", True)))
    return templates.TemplateResponse(
        request, "report.html", {"papers": papers, "publishers": publisher_names}
    )


@app.post("/report/generate")
async def generate_report(request: Request):
    body = await request.json()
    dois = body.get("dois", [])

    db = DatabaseClient(DB_PATH)
    db.init_db_papers()

    from pipeline.phase_g import phase_g_report
    phase_g_report(db, REPORT_DIR, doi_list=dois)

    # Find latest report
    report_dir = Path(REPORT_DIR)
    md_files = sorted(report_dir.glob("report_*.md"), reverse=True)
    filename = md_files[0].name if md_files else ""
    preview = md_files[0].read_text(encoding="utf-8") if md_files else ""
    return JSONResponse({"ok": True, "filename": filename, "preview": preview})


@app.get("/report/download/{filename:path}")
async def download_report(filename: str):
    file_path = REPORT_DIR / filename
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(str(file_path), filename=filename, media_type="text/markdown")


# ── Logs ──────────────────────────────────────────────────────────────────────

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    log_path = Path(LOG_FILE_PATH)
    log_content = ""
    if log_path.exists():
        log_content = log_path.read_text(encoding="utf-8", errors="replace")[-200000:]
    return templates.TemplateResponse(request, "logs.html", {"log_content": log_content})


# ── Config ─────────────────────────────────────────────────────────────────────

@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    publishers = load_publishers()
    keywords = load_keywords()
    skip_config = _get_effective_skip()
    overrides_raw = json.dumps(_load_skip_overrides(), indent=2)
    config_dir = CONFIG_DIR
    publishers_raw = (config_dir / "publishers.yaml").read_text(encoding="utf-8")
    keywords_raw = (config_dir / "keywords.yaml").read_text(encoding="utf-8")
    return templates.TemplateResponse(request, "config.html", {
        "publishers": publishers, "keywords": keywords,
        "skip_config": skip_config, "overrides_raw": overrides_raw,
        "publishers_raw": publishers_raw, "keywords_raw": keywords_raw,
    })


@app.post("/config/skip-toggle/{phase}")
async def config_skip_toggle(phase: str):
    if phase not in PHASE_LABELS:
        return JSONResponse({"error": f"Unknown phase: {phase}"}, status_code=400)
    overrides = _load_skip_overrides()
    current = overrides.get(phase, PHASE_DEFAULTS[phase])
    overrides[phase] = not current
    SKIP_OVERRIDES_PATH.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
    return JSONResponse({"ok": True, "phase": phase, "skipped": overrides[phase]})


@app.post("/config/save-publishers")
async def config_save_publishers(request: Request):
    body = await request.json()
    content = body.get("content", "")
    try:
        import yaml
        parsed = yaml.safe_load(content)
    except Exception as e:
        return JSONResponse({"error": f"YAML syntax error: {e}"}, status_code=400)
    path = CONFIG_DIR / "publishers.yaml"
    path.write_text(content, encoding="utf-8")
    return JSONResponse({"ok": True, "path": str(path)})


@app.post("/config/save-keywords")
async def config_save_keywords(request: Request):
    body = await request.json()
    content = body.get("content", "")
    try:
        import yaml
        parsed = yaml.safe_load(content)
    except Exception as e:
        return JSONResponse({"error": f"YAML syntax error: {e}"}, status_code=400)
    path = CONFIG_DIR / "keywords.yaml"
    path.write_text(content, encoding="utf-8")
    return JSONResponse({"ok": True, "path": str(path)})
