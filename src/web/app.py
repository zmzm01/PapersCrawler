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
    DB_PATH, REPORT_DIR, AUTO_REPORT_DIR, USER_REPORT_DIR,
    LOG_FILE_PATH, DATA_DIR, CONFIG_DIR,
    load_publishers, load_keywords,
    SKIP_PHASE_A_RSS, SKIP_PHASE_A_CR,
    SKIP_PHASE_B, SKIP_PHASE_C, SKIP_PHASE_D,
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
    "A-RSS": "RSS Fetch", "A-CR": "CrossRef Query",
    "B": "CrossRef Metadata", "C": "Publisher Page",
    "D": "Semantic Filter", "E": "LLM Relevance", "E2": "MinerU PDF",
    "F": "LLM Summary", "G": "Report", "H": "Email",
}

PHASE_DEFAULTS = {
    "A-RSS": SKIP_PHASE_A_RSS, "A-CR": SKIP_PHASE_A_CR,
    "B": SKIP_PHASE_B, "C": SKIP_PHASE_C,
    "D": SKIP_PHASE_D, "E": SKIP_PHASE_E, "E2": SKIP_PHASE_E2,
    "F": SKIP_PHASE_F, "G": SKIP_PHASE_G, "H": SKIP_PHASE_H,
}

PHASE_ORDER = ["A-RSS", "A-CR", "B", "C", "D", "E", "E2", "F", "G", "H"]

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
    effective_skip = {k: _get_effective_skip().get(k, False) for k in PHASE_ORDER}
    return {"total": total, "phases": phases, "effective_skip": effective_skip}


# Reset definitions: (columns_to_pending, cascade_info, extra_where)
RESET_DEFS = {
    "B": (["cr_metadata_fetched_status"], "cr_metadata_fetched_status != 'pending'", None),
    "C": (["publisher_page_fetched_status", "publisher_page_fetched_error"],
          "publisher_page_fetched_status IN ('failed','skipped') "
          "AND (publisher_page_fetched_error IS NULL "
          "OR publisher_page_fetched_error NOT LIKE 'NonResearchPageError:%')",
          None),
    "D": (["semantic_filter_status", "semantic_filter_error",
           "semantic_similarity_score", "semantic_best_subdomain"],
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
    "B": "", "C": "", "D": "",
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
        request, "home.html", {
            "publisher_count": p_count,
            "paper_count": total,
            "phase_count": len(PHASE_ORDER),
        }
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
    effective = _get_effective_skip()
    if effective.get(phase, False):
        return JSONResponse({"error": f"Phase {phase} is skipped in Config — enable it first"}, status_code=400)
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


def _get_reset_cols(phase: str) -> list[str]:
    """Derive the list of status column names for a given reset phase."""
    cols, _, _ = RESET_DEFS[phase]
    col_names = [c for i, c in enumerate(cols) if i % 2 == 0]
    return list(dict.fromkeys(col_names))


def _count_reset_impact(phase: str, reset_cols: list[str]) -> dict[str, int]:
    """Count papers affected per column for a reset operation (read-only).

    For Phase D, skip REAL/NULL columns (semantic_similarity_score,
    semantic_best_subdomain) — count only on the primary status column.
    """
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    status_cols = [c for c in reset_cols
                   if c not in ("semantic_similarity_score", "semantic_best_subdomain")]
    impact = {}
    for c in status_cols:
        cur = db.conn.execute(
            f"SELECT COUNT(*) FROM papers WHERE {c} IN ('success','failed','skipped')"
        )
        impact[c] = cur.fetchone()[0]
    return impact


def _execute_reset(phase: str, reset_cols: list[str]):
    """Execute the reset for the given columns."""
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    for c in reset_cols:
        if c in ("semantic_similarity_score", "semantic_best_subdomain"):
            # Non-status columns → set to NULL
            db.batch_reset_status(
                [(c, None)],
                "semantic_filter_status IN ('success','failed','skipped')",
            )
        else:
            db.batch_reset_status(
                [(c, "pending")],
                f"{c} IN ('success','failed','skipped')",
            )


@app.post("/pipeline/reset/{phase}")
async def reset_preview(phase: str):
    """Preview reset impact — counts affected papers without mutating DB."""
    if phase not in RESET_DEFS:
        return JSONResponse({"error": f"Unsupported reset phase: {phase}"}, status_code=400)
    reset_cols = _get_reset_cols(phase)
    impact = _count_reset_impact(phase, reset_cols)
    return JSONResponse({"ok": True, "phase": phase, "impact": impact})


@app.post("/pipeline/reset/{phase}/execute")
async def reset_execute(phase: str):
    """Execute the reset after user confirmation."""
    if phase not in RESET_DEFS:
        return JSONResponse({"error": f"Unsupported reset phase: {phase}"}, status_code=400)
    reset_cols = _get_reset_cols(phase)
    impact = _count_reset_impact(phase, reset_cols)
    _execute_reset(phase, reset_cols)
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
async def papers_page(request: Request, sort: str = "created"):
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    sort_by = sort if sort in ("created", "published") else "created"
    papers = db.get_papers(limit=100, sort_by=sort_by)
    return templates.TemplateResponse(request, "papers.html", {
        "papers": papers, "sort_by": sort_by,
    })


# ── Report ─────────────────────────────────────────────────────────────────────


def _list_reports():
    """List all report files from auto/ and user/ directories, newest first."""
    reports = []
    for source, directory in [("auto", AUTO_REPORT_DIR), ("user", USER_REPORT_DIR)]:
        if not directory.exists():
            continue
        for f in sorted(directory.glob("report_*.md"), reverse=True):
            reports.append({
                "filename": f.name,
                "source": source,
                "path": str(f.relative_to(DATA_DIR.parent)),
                "mtime": f.stat().st_mtime,
            })
    reports.sort(key=lambda r: r["mtime"], reverse=True)
    return reports


@app.get("/report", response_class=HTMLResponse)
async def report_page(request: Request):
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    papers = db.get_papers_with_summaries()
    publishers = load_publishers()
    publisher_names = sorted(set(p["publisher"] for p in publishers if p.get("enabled", True)))
    reports = _list_reports()
    return templates.TemplateResponse(
        request, "report.html", {
            "papers": papers, "publishers": publisher_names, "reports": reports,
        }
    )


@app.get("/report/list")
async def report_list():
    return JSONResponse({"ok": True, "reports": _list_reports()})


@app.get("/report/data/{filename:path}")
async def report_data(filename: str):
    for directory in [AUTO_REPORT_DIR, USER_REPORT_DIR]:
        file_path = directory / filename
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            return JSONResponse({"ok": True, "content": content, "filename": filename})
    return JSONResponse({"error": "Report not found"}, status_code=404)


@app.post("/report/generate")
async def generate_report(request: Request):
    body = await request.json()
    dois = body.get("dois", [])

    db = DatabaseClient(DB_PATH)
    db.init_db_papers()

    from pipeline.phase_g import phase_g_report
    phase_g_report(db, AUTO_REPORT_DIR, USER_REPORT_DIR, doi_list=dois)

    # Find latest user report
    user_dir = Path(USER_REPORT_DIR)
    md_files = sorted(user_dir.glob("report_*.md"), reverse=True)
    filename = md_files[0].name if md_files else ""
    preview = md_files[0].read_text(encoding="utf-8") if md_files else ""
    return JSONResponse({"ok": True, "filename": filename, "preview": preview})


@app.get("/report/download/{filename:path}")
async def download_report(filename: str):
    for directory in [AUTO_REPORT_DIR, USER_REPORT_DIR]:
        file_path = directory / filename
        if file_path.exists():
            return FileResponse(str(file_path), filename=filename, media_type="text/markdown")
    return JSONResponse({"error": "File not found"}, status_code=404)


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
    domain_description = keywords.get("domain_description", "")
    return templates.TemplateResponse(request, "config.html", {
        "publishers": publishers, "keywords": keywords,
        "skip_config": skip_config, "overrides_raw": overrides_raw,
        "publishers_raw": publishers_raw, "keywords_raw": keywords_raw,
        "domain_description": domain_description,
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


@app.get("/config/mineru-token")
async def config_mineru_token_status():
    import base64, time
    token = os.getenv("MINERU_TOKEN", "")
    if not token:
        return JSONResponse({"ok": True, "valid": False, "error": "Not configured"})
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return JSONResponse({"ok": True, "valid": False, "error": "Invalid JWT format"})
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.b64decode(payload))
        exp = data.get("exp", 0)
        if not exp:
            return JSONResponse({"ok": True, "valid": True, "days_left": None})
        days_left = (exp - time.time()) / 86400
        return JSONResponse({"ok": True, "valid": True, "days_left": round(days_left, 1)})
    except Exception as e:
        return JSONResponse({"ok": True, "valid": False, "error": str(e)})


@app.post("/config/test-deepseek")
async def config_test_deepseek():
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key.startswith("sk-placeholder"):
        return JSONResponse({"ok": False, "error": "DEEPSEEK_API_KEY not configured"})
    try:
        import requests
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return JSONResponse({"ok": True})
        else:
            return JSONResponse({"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/config/test-crossref")
async def config_test_crossref():
    try:
        import requests
        resp = requests.get(
            "https://api.crossref.org/works/10.1038/nature12373",
            headers={"User-Agent": "PaperCrawler (mailto:test@example.com) Python"},
            timeout=10,
        )
        if resp.status_code == 200:
            return JSONResponse({"ok": True})
        else:
            return JSONResponse({"ok": False, "error": f"HTTP {resp.status_code}"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/config/save-domain")
async def config_save_domain(request: Request):
    body = await request.json()
    content = body.get("content", "")
    try:
        from ruamel.yaml import YAML
        kw_path = CONFIG_DIR / "keywords.yaml"
        ryaml = YAML()
        kw = ryaml.load(kw_path)
        if kw is None or not isinstance(kw, dict):
            kw = {"domain_description": content}
        else:
            kw["domain_description"] = content
        ryaml.dump(kw, kw_path)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/config/test-mineru")
async def config_test_mineru():
    token = os.getenv("MINERU_TOKEN", "")
    if not token:
        return JSONResponse({"ok": False, "error": "MINERU_TOKEN not configured"})
    try:
        import requests
        resp = requests.get(
            "https://mineru.net/api/v1/user/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return JSONResponse({"ok": True})
        else:
            return JSONResponse({"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


# ── Data Sources ──────────────────────────────────────────────────────────────

JOURNAL_OVERRIDES_PATH = DATA_DIR / "journal_overrides.json"


def _load_journal_overrides():
    if not JOURNAL_OVERRIDES_PATH.exists():
        return {"journals": {}}
    try:
        return json.loads(JOURNAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return {"journals": {}}


def _journal_override_value(jid, overrides, field):
    ov = overrides.get("journals", {}).get(jid, {})
    if field in ov:
        return ov[field]
    if field in ("rss_enabled", "cr_enabled") and "enabled" in ov:
        return ov["enabled"]
    return None


@app.get("/datasources", response_class=HTMLResponse)
async def datasources_page(request: Request):
    publishers = load_publishers()
    overrides = _load_journal_overrides()
    journals = []
    for j in publishers:
        jid = j["id"]
        ov = overrides.get("journals", {}).get(jid, {})
        enabled_default = j.get("enabled", True)
        override_enabled = _journal_override_value(jid, overrides, "enabled")
        if override_enabled is not None:
            override_enabled = bool(override_enabled)
        else:
            override_enabled = bool(enabled_default)
        override_rss = _journal_override_value(jid, overrides, "rss_enabled")
        if override_rss is None:
            override_rss = override_enabled
        else:
            override_rss = bool(override_rss)
        override_cr = _journal_override_value(jid, overrides, "cr_enabled")
        if override_cr is None:
            override_cr = override_enabled
        else:
            override_cr = bool(override_cr)
        journals.append({
            "id": jid,
            "name": j.get("name", ""),
            "publisher": j.get("publisher", ""),
            "issn": j.get("issn", ""),
            "has_rss": bool(j.get("rss")),
            "has_issn": bool(j.get("issn")),
            "enabled_default": bool(enabled_default),
            "override_enabled": override_enabled,
            "override_rss": override_rss,
            "override_cr": override_cr,
        })
    return templates.TemplateResponse(request, "datasources.html", {"journals": journals})


@app.post("/datasources/save")
async def datasources_save(request: Request):
    body = await request.json()
    journals = body.get("journals", {})
    overrides = {"journals": journals}
    JOURNAL_OVERRIDES_PATH.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
    return JSONResponse({"ok": True, "path": str(JOURNAL_OVERRIDES_PATH)})


# ── Subscriptions ─────────────────────────────────────────────────────────────

@app.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(request: Request):
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    subscribers = db.get_subscribers(active_only=False)
    subs_list = []
    for s in subscribers:
        subs_list.append({
            "email": s["email"],
            "name": s["name"] or "",
            "active": bool(s["active"]),
            "created_date": s["created_date"] or "",
        })
    return templates.TemplateResponse(request, "subscriptions.html", {
        "subscribers": subs_list,
    })


@app.post("/subscriptions/add")
async def subscriptions_add(request: Request):
    body = await request.json()
    email = body.get("email", "").strip().lower()
    name = body.get("name", "").strip()
    if not email or "@" not in email:
        return JSONResponse({"ok": False, "error": "Invalid email"})
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    ok = db.add_subscriber(email, name)
    return JSONResponse({"ok": ok, "error": None if ok else "Duplicate email"})


@app.post("/subscriptions/remove")
async def subscriptions_remove(request: Request):
    body = await request.json()
    email = body.get("email", "")
    if not email:
        return JSONResponse({"ok": False, "error": "Missing email"})
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    db.remove_subscriber(email)
    return JSONResponse({"ok": True})


@app.post("/subscriptions/toggle")
async def subscriptions_toggle(request: Request):
    body = await request.json()
    email = body.get("email", "")
    active = body.get("active", True)
    if not email:
        return JSONResponse({"ok": False, "error": "Missing email"})
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    db.toggle_subscriber(email, 1 if active else 0)
    return JSONResponse({"ok": True})


@app.post("/subscriptions/import-from-env")
async def subscriptions_import_env():
    from config import load_email_config
    cfg = load_email_config()
    to_addrs = cfg.get("to_addrs", []) if cfg else []
    db = DatabaseClient(DB_PATH)
    db.init_db_papers()
    imported = 0
    for addr in to_addrs:
        if db.add_subscriber(addr.strip().lower()):
            imported += 1
    return JSONResponse({"ok": True, "imported": imported})


@app.post("/subscriptions/test/{email}")
async def subscriptions_test(email: str):
    from config import load_email_config
    from processors.email_sender import EmailSender
    cfg = load_email_config()
    if not cfg:
        return JSONResponse({"ok": False, "error": "SMTP not configured"})
    try:
        sender = EmailSender(
            smtp_host=cfg["smtp_host"],
            smtp_port=cfg["smtp_port"],
            username=cfg["username"],
            password=cfg["password"],
            from_addr=cfg["from_addr"],
            to_addrs=[email],
            use_tls=cfg.get("use_tls", True),
        )
        sender.send(
            subject="PapersCrawler Test",
            body="This is a test message from PapersCrawler.\n\nIf you received this, SMTP configuration is working.",
            body_type="plain",
        )
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
