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

# Ensure src/ is importable (same convention as rest of project)
_src_path = Path(__file__).resolve().parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    DB_PATH, REPORT_DIR, LOG_FILE_PATH,
    load_publishers, load_keywords,
    SKIP_PHASE_A, SKIP_PHASE_B, SKIP_PHASE_C, SKIP_PHASE_D,
    SKIP_PHASE_E, SKIP_PHASE_E2, SKIP_PHASE_F, SKIP_PHASE_G, SKIP_PHASE_H,
)
from db.database import DatabaseClient

app = FastAPI(title="PapersCrawler")

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

_running_phase: Optional[str] = None
_phase_lock = asyncio.Lock()

PHASE_LABELS = {
    "A": "RSS Fetch",
    "B": "CrossRef Metadata",
    "C": "Publisher Page",
    "D": "Semantic Filter",
    "E": "LLM Relevance",
    "E2": "MinerU PDF",
    "F": "LLM Summary",
    "G": "Report",
    "H": "Email",
}

PHASE_SKIP = {
    "A": SKIP_PHASE_A, "B": SKIP_PHASE_B, "C": SKIP_PHASE_C,
    "D": SKIP_PHASE_D, "E": SKIP_PHASE_E, "E2": SKIP_PHASE_E2,
    "F": SKIP_PHASE_F, "G": SKIP_PHASE_G, "H": SKIP_PHASE_H,
}


# ── Helper ────────────────────────────────────────────────────────────────────

def _pipeline_status():
    """Query DB for pipeline phase status counts."""
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    papers = db.get_all_papers()
    total = len(papers)

    status_cols = [
        ("cr_metadata_fetched", "cr_metadata_fetched_status"),
        ("publisher_page", "publisher_page_fetched_status"),
        ("semantic_filter", "semantic_filter_status"),
        ("llm_relevance", "llm_relevance_status"),
        ("mineru_parse", "mineru_parse_status"),
        ("llm_summary", "llm_summary_status"),
    ]

    phases = {}
    for label, col in status_cols:
        counts = {"success": 0, "failed": 0, "skipped": 0, "pending": 0}
        for p in papers:
            status = p[col] if p[col] else "pending"
            if status in counts:
                counts[status] += 1
            else:
                counts["pending"] += 1
        phases[label] = counts

    return {"total": total, "phases": phases}


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    status = _pipeline_status()
    return templates.TemplateResponse(
        request, "dashboard.html", {"status": status}
    )


@app.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request):
    phase_keys = list(PHASE_LABELS.keys())
    phases = [
        {"key": k, "label": PHASE_LABELS[k], "skipped": PHASE_SKIP.get(k, False)}
        for k in phase_keys
    ]
    return templates.TemplateResponse(
        request, "pipeline.html", {"phases": phases}
    )


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

    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"

    def _run():
        global _running_phase
        try:
            subprocess.run(
                [sys.executable, "-c",
                 f"import sys; sys.path.insert(0, '{src_dir}'); "
                 f"from pipeline.runner import run_phases; "
                 f"run_phases({[phase]!r}, force=True)"],
                cwd=project_root,
                capture_output=True,
                timeout=3600,
            )
        except subprocess.TimeoutExpired:
            pass
        finally:
            _running_phase = None

    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return JSONResponse({"ok": True, "phase": phase})


@app.post("/pipeline/run-all")
async def run_all():
    global _running_phase
    async with _phase_lock:
        if _running_phase:
            return JSONResponse({"error": f"Phase {_running_phase} is already running"}, status_code=409)
        _running_phase = "ALL"

    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"

    def _run():
        global _running_phase
        try:
            subprocess.run(
                [sys.executable, "-c",
                 f"import sys; sys.path.insert(0, '{src_dir}'); "
                 f"from pipeline.runner import run_pipeline; "
                 f"run_pipeline(force=True)"],
                cwd=project_root,
                capture_output=True,
                timeout=14400,
            )
        except subprocess.TimeoutExpired:
            pass
        finally:
            _running_phase = None

    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return JSONResponse({"ok": True, "phase": "ALL"})


async def _log_event_stream():
    """SSE stream: tail the pipeline log file."""
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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    log_path = Path(LOG_FILE_PATH)
    log_content = ""
    if log_path.exists():
        log_content = log_path.read_text(encoding="utf-8", errors="replace")[-200000:]
    return templates.TemplateResponse(
        request, "logs.html", {"log_content": log_content}
    )


@app.get("/report", response_class=HTMLResponse)
async def report_page(request: Request):
    publishers = load_publishers()
    publisher_names = sorted(set(p["publisher"] for p in publishers if p.get("enabled", True)))
    return templates.TemplateResponse(
        request, "report.html", {"publishers": publisher_names}
    )


@app.post("/report/generate")
async def generate_report(publisher: Optional[str] = None):
    from pipeline.runner import run_phases
    run_phases(["G"])
    return JSONResponse({"ok": True})


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    publishers = load_publishers()
    keywords = load_keywords()

    skip_config = {k: PHASE_SKIP[k] for k in PHASE_LABELS}

    # Load raw YAML content for display
    config_dir = Path(__file__).parent.parent.parent / "configs"
    publishers_raw = (config_dir / "publishers.yaml").read_text(encoding="utf-8")
    keywords_raw = (config_dir / "keywords.yaml").read_text(encoding="utf-8")

    return templates.TemplateResponse(
        request, "config.html", {
            "publishers": publishers,
            "keywords": keywords,
            "skip_config": skip_config,
            "publishers_raw": publishers_raw,
            "keywords_raw": keywords_raw,
        }
    )
