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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Ensure src/ is importable
_src_path = Path(__file__).resolve().parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

import logging
import os as _os

from config import DATA_DIR, LOG_FILE_PATH

DATA_DIR.mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
console_handler = logging.StreamHandler()
logging.basicConfig(
    level=getattr(logging, _os.getenv("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[file_handler, console_handler],
)
logger = logging.getLogger(__name__)

# 在 logging.basicConfig 配置完成后再检测 token，避免 warning 偷装默认 handler
from config import _check_mineru_token
_check_mineru_token()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from config import (
    CFG,
    DB_PATH, REPORT_DIR, AUTO_REPORT_DIR, USER_REPORT_DIR,
    LOG_FILE_PATH, DATA_DIR, CONFIG_DIR, PROMPTS_DIR,
    JOURNAL_OVERRIDES_PATH, EMAIL_TEMPLATE_DIR,
    load_publishers, load_keywords, load_settings,
)
from db.database import DatabaseClient

app = FastAPI(title="PapersCrawler")


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """注入安全响应头防止 clickjacking / MIME sniffing / 信息泄露。"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))


app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

_running_phase: Optional[str] = None
_phase_lock = asyncio.Lock()

PHASE_LABELS = {
    "A-RSS": "RSS Fetch", "A-CR": "CrossRef Query",
    "B": "CrossRef Metadata", "C": "Publisher Page",
    "E": "LLM Relevance", "E2": "MinerU PDF",
    "F": "LLM Summary", "G": "Report", "H": "Email",
}

PHASE_ORDER = ["A-RSS", "A-CR", "B", "C", "E", "E2", "F", "G", "H"]

# 从 CFG 读取阶段默认值的映射表
_PHASE_KEY_MAP = {
    "A-RSS": "SKIP_PHASE_A_RSS", "A-CR": "SKIP_PHASE_A_CR",
    "B": "SKIP_PHASE_B", "C": "SKIP_PHASE_C",
    "E": "SKIP_PHASE_E", "E2": "SKIP_PHASE_E2",
    "F": "SKIP_PHASE_F", "G": "SKIP_PHASE_G", "H": "SKIP_PHASE_H",
}

def _atomic_write(path, content):
    """原子写入文件：先写 .tmp，再 os.replace 原子替换。"""
    import tempfile as _tempfile
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        _tempfile._os.replace(str(tmp_path), str(path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _get_effective_skip():
    return {k: getattr(CFG, _PHASE_KEY_MAP[k]) for k in _PHASE_KEY_MAP}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _classify_error(error_text: str) -> str:
    """Classify an error message into a user-friendly category."""
    e = (error_text or "").lower()
    if not e:
        return "Unknown"
    patterns = [
        (["cloudflare", "bot block", "challenge-platform",
          "cf-ray", "turnstile", "radware", "bot manager"], "Bot / Cloudflare"),
        (["nonresearchpageerror", "non-research",
          "not a research article", "nonresearchprefetch"], "Non-research article"),
        (["timeout", "connection refused", "connection error",
          "connection unexpectedly closed"], "Network / Timeout"),
        (["llmapicallerror", "llmresponseparseerror",
          "llmconfigurationerror", "llmcontextlengthexceed",
          "api key", "apikey", "401", "402", "429", "500", "502", "503"], "LLM API Error"),
        (["mineru", "parse_pdf", "pdf parse"], "MinerU Error"),
        (["pageparseerror", "page structure",
          "citation_", "no dc.type", "metadata"], "Page Parse Error"),
        (["empty", "not found", "404", "no mineru"], "Data Missing"),
        (["publisher disabled"], "Publisher Disabled"),
    ]
    for keywords, category in patterns:
        for kw in keywords:
            if kw in e:
                return category
    return "Other"


def _pipeline_status():
    db = DatabaseClient(DB_PATH)
    try:
        db.init_db_papers()
        total = len(db.get_all_papers())
        stats = db.get_phase_stats()
        phases = {}
        for ps in stats:
            counts = ps["status_counts"]
            out = dict(counts)
            # Classify error texts into user-friendly categories
            breakdown: dict[str, int] = {}
            for err_text in ps["error_texts"]:
                cat = _classify_error(err_text)
                breakdown[cat] = breakdown.get(cat, 0) + 1
            if breakdown:
                out["failed_breakdown"] = breakdown
            phases[ps["label"]] = out
        effective_skip = {k: _get_effective_skip().get(k, False) for k in PHASE_ORDER}
        # Count papers pending report: A/B 相关 + LLM 总结成功 + 尚未被报告
        pending_report = db.conn.execute(
            "SELECT COUNT(*) FROM papers "
            "WHERE llm_summary_status = 'success' "
            "  AND report_date IS NULL "
            "  AND llm_relevance_status = 'success' "
            "  AND llm_relevance_category IN ('A', 'B')"
        ).fetchone()[0]
        return {
            "total": total,
            "phases": phases,
            "effective_skip": effective_skip,
            "pending_report": pending_report,
        }
    finally:
        db.conn.close()


# Reset definitions: (columns_to_pending, cascade_info, extra_where)
RESET_DEFS = {
    "B": (["cr_metadata_fetched_status"], "cr_metadata_fetched_status != 'pending'", None),
    "C": (["publisher_page_fetched_status", "publisher_page_fetched_error"],
          "publisher_page_fetched_status IN ('failed','skipped') "
          "AND (publisher_page_fetched_error IS NULL "
          "OR publisher_page_fetched_error NOT LIKE 'NonResearchPageError:%')",
          None),
    "E": (["llm_relevance_status", "llm_relevance_category", "llm_relevance_subfields",
           "llm_relevance_confidence", "llm_relevance_reason", "llm_relevance_error"],
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
    log_path = Path(LOG_FILE_PATH)

    def _run():
        global _running_phase
        try:
            # 子进程需要自己的 logging 配置，才能写入共享日志文件
            log_file_abs = str(log_path.resolve())
            if is_all:
                code = (
                    "import logging, sys;"
                    f"logging.basicConfig(level=logging.DEBUG,"
                    f" format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',"
                    f" datefmt='%Y-%m-%d %H:%M:%S',"
                    f" handlers=[logging.FileHandler(r'{log_file_abs}', encoding='utf-8'),"
                    f"           logging.StreamHandler(sys.stderr)]);"
                    "from pipeline.runner import run_pipeline;"
                    "run_pipeline(run_all=True)"
                )
            else:
                code = (
                    "import logging, sys;"
                    f"logging.basicConfig(level=logging.DEBUG,"
                    f" format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',"
                    f" datefmt='%Y-%m-%d %H:%M:%S',"
                    f" handlers=[logging.FileHandler(r'{log_file_abs}', encoding='utf-8'),"
                    f"           logging.StreamHandler(sys.stderr)]);"
                    f"from pipeline.runner import run_phases;"
                    f"run_phases({[phase]!r}, force=True)"
                )
            logger.info(f"Subprocess starting: phase={phase}, is_all={is_all}")
            result = subprocess.run(
                [sys.executable, "-c", f"import sys; sys.path.insert(0, '{src_dir}'); {code}"],
                cwd=project_root, timeout=14400 if is_all else 3600,
            )
            if result.returncode != 0:
                logger.warning(f"Subprocess phase={phase} exited with code {result.returncode}")
            else:
                logger.info(f"Subprocess phase={phase} completed successfully")
        except subprocess.TimeoutExpired:
            logger.warning(f"Subprocess phase={phase} timed out")
        except Exception as e:
            logger.error(f"Subprocess phase={phase} failed: {e}")
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
    try:
        db.init_db_papers()
        total = len(db.get_all_papers())
    finally:
        db.conn.close()
    return templates.TemplateResponse(
        request, "home.html", {
            "publisher_count": p_count,
            "paper_count": total,
            "phase_count": len(PHASE_ORDER),
        }
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    status_data = _pipeline_status()
    publishers = load_publishers()
    return templates.TemplateResponse(
        request, "dashboard.html", {
            "publisher_count": len(publishers),
            "phase_count": len(PHASE_ORDER),
            "initial_status": status_data,
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


@app.get("/pipeline/weekly-stats")
async def pipeline_weekly_stats():
    """Return per-day stats for the last 7 days: total discovered, reportable, summary_failed."""
    db = DatabaseClient(DB_PATH)
    try:
        db.init_db_papers()
        today = datetime.now()
        # Build 7-day date list (today-6 ... today)
        days = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            days.append({
                "date": d.strftime("%Y%m%d"),
                "weekday": d.strftime("%a"),
                "total": 0,
                "reportable": 0,
                "summary_failed": 0,
            })

        day_start = days[0]["date"]
        day_end = days[-1]["date"]
        rows = db.conn.execute("""
            SELECT
              created_date AS day,
              COUNT(*) AS total,
              SUM(CASE WHEN llm_summary_status = 'success' AND report_date IS NULL
                       THEN 1 ELSE 0 END) AS reportable,
              SUM(CASE WHEN publisher_page_fetched_status = 'failed'
                       THEN 1 ELSE 0 END) AS publisher_failed,
              SUM(CASE WHEN mineru_parse_status = 'failed'
                       THEN 1 ELSE 0 END) AS mineru_failed,
              SUM(CASE WHEN llm_summary_status = 'failed'
                       THEN 1 ELSE 0 END) AS summary_failed,
              SUM(CASE WHEN publisher_page_fetched_status = 'failed'
                        OR mineru_parse_status = 'failed'
                        OR llm_summary_status = 'failed'
                       THEN 1 ELSE 0 END) AS total_failed
            FROM papers
            WHERE created_date >= ? AND created_date <= ?
            GROUP BY created_date
            ORDER BY created_date
        """, (day_start, day_end)).fetchall()

        day_map = {r["day"]: r for r in rows}
        for d in days:
            r = day_map.get(d["date"])
            if r:
                d["total"] = r["total"]
                d["reportable"] = r["reportable"]
                d["publisher_failed"] = r["publisher_failed"]
                d["mineru_failed"] = r["mineru_failed"]
                d["summary_failed"] = r["summary_failed"]
                d["total_failed"] = r["total_failed"]

        return {"ok": True, "days": days}
    finally:
        db.conn.close()





async def _log_event_stream():
    log_path = Path(LOG_FILE_PATH)
    first_read = True
    last_size = log_path.stat().st_size if log_path.exists() else 0
    while True:
        if log_path.exists():
            current_size = log_path.stat().st_size
            if first_read:
                # 首次连接：发送文件尾部 ~200KB，让用户看到已有日志
                with open(log_path, "r", encoding="utf-8") as f:
                    if current_size > 200 * 1024:
                        f.seek(current_size - 200 * 1024)
                        f.readline()  # 跳过可能截断的行
                    existing = f.read()
                    if existing:
                        yield f"data: {json.dumps({'text': existing})}\n\n"
                first_read = False
                last_size = current_size
            elif current_size > last_size:
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
async def papers_page(
    request: Request,
    sort: str = "created",
    category: str = "ab",
    has_summary: bool = False,
    page: int = 1,
    per_page: int = 100,
):
    db = DatabaseClient(DB_PATH)
    try:
        db.init_db_papers()
        sort_by = sort if sort in ("created", "published", "summary") else "created"
        category_filter = category if category in ("a", "b", "ab", "all") else "ab"
        per_page = per_page if per_page in (50, 100, 200) else 100
        page = page if page >= 1 else 1
        offset = (page - 1) * per_page
        papers = db.get_papers(limit=per_page, offset=offset, sort_by=sort_by, category_filter=category_filter)
        if has_summary:
            papers = [p for p in papers if getattr(p, "llm_summary_status", None) == "success"]
        total_count = db.get_papers_count(category_filter=category_filter)
    finally:
        db.conn.close()
    return templates.TemplateResponse(request, "papers.html", {
        "papers": papers, "sort_by": sort_by, "category_filter": category_filter,
        "has_summary_filter": has_summary,
        "page": page, "per_page": per_page, "total_count": total_count,
    })


# ── Report ─────────────────────────────────────────────────────────────────────


def _timeago(timestamp: float) -> str:
    """Return a human-readable relative time string for a Unix timestamp."""
    if not timestamp:
        return ""
    delta = datetime.now() - datetime.fromtimestamp(timestamp)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    return f"{seconds // 604800}w ago"


def _list_reports():
    """List all report files from auto/ and user/ directories, newest first."""
    reports = []
    for source, directory in [("auto", AUTO_REPORT_DIR), ("user", USER_REPORT_DIR)]:
        if not directory.exists():
            continue
        for f in sorted(directory.glob("report_*.md"), reverse=True):
            mtime = f.stat().st_mtime
            content = f.read_text(encoding="utf-8")
            paper_count = content.count("**DOI**")
            reports.append({
                "filename": f.name,
                "source": source,
                "path": str(f.relative_to(DATA_DIR.parent)),
                "mtime": mtime,
                "timeago": _timeago(mtime),
                "paper_count": paper_count,
            })
    reports.sort(key=lambda r: r["mtime"], reverse=True)
    return reports


@app.get("/report", response_class=HTMLResponse)
async def report_page(request: Request, show: str = ""):
    reports = _list_reports()
    selected_filename = show
    if not selected_filename and reports:
        selected_filename = reports[0]["filename"]
    return templates.TemplateResponse(
        request, "report.html", {
            "reports": reports, "selected_filename": selected_filename,
        }
    )


@app.get("/report/list")
async def report_list():
    return JSONResponse({"ok": True, "reports": _list_reports()})


@app.get("/report/data/{filename:path}")
async def report_data(filename: str):
    for directory in [AUTO_REPORT_DIR, USER_REPORT_DIR]:
        file_path = (directory / filename).resolve()
        # 防止 ../../etc/passwd 这类路径遍历
        if not str(file_path).startswith(str(directory.resolve())):
            return JSONResponse({"error": "Invalid path"}, status_code=400)
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            return JSONResponse({"ok": True, "content": content, "filename": filename})
    return JSONResponse({"error": "Report not found"}, status_code=404)





@app.get("/report/download/{filename:path}")
async def download_report(filename: str):
    for directory in [AUTO_REPORT_DIR, USER_REPORT_DIR]:
        file_path = (directory / filename).resolve()
        # 防止 ../../etc/passwd 这类路径遍历
        if not str(file_path).startswith(str(directory.resolve())):
            return JSONResponse({"error": "Invalid path"}, status_code=400)
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













