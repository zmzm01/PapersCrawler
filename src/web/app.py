"""
PapersCrawler Web UI — FastAPI application.

Provides a web interface for dashboard monitoring and report viewing.

Usage:
    PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080

    # On headless server (Phase C needs display):
    xvfb-run -a bash -c 'PYTHONPATH=src uvicorn src.web.app:app --host 0.0.0.0 --port 8080'
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ensure src/ is importable
_src_path = Path(__file__).resolve().parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

import logging
import os
import threading
from urllib.parse import quote, urlencode, urlsplit

from pydantic import BaseModel

from config import DATA_DIR
from logging_config import configure_logging, resolve_log_dir

configure_logging(
    os.getenv("LOG_LEVEL", "DEBUG"),
    resolve_log_dir(DATA_DIR / "logs"),
)
logger = logging.getLogger(__name__)

# 在 logging.basicConfig 配置完成后再检测 token，避免 warning 偷装默认 handler
from config import _check_mineru_token
_check_mineru_token()

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    DB_PATH, AUTO_REPORT_DIR, USER_REPORT_DIR,
    DATA_DIR, load_publishers,
)
from db.database import (
    DataBaseDOINotExists,
    DatabaseClient,
    EFFECTIVE_RELEVANCE_CATEGORY_SQL,
    LATEST_RELEVANCE_REVIEW_CTE,
)

app = FastAPI(title="PapersCrawler")


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """注入安全响应头防止 clickjacking / MIME sniffing / 信息泄露。"""
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled WebUI request: method=%s path=%s",
            request.method,
            request.url.path,
        )
        if request.url.path.startswith("/pipeline/"):
            response = JSONResponse(
                {"ok": False, "detail": "Internal server error"},
                status_code=500,
            )
        else:
            response = HTMLResponse("Internal server error", status_code=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))

app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


class RelevanceReviewPayload(BaseModel):
    """JSON payload submitted by the manual relevance review form."""

    doi: str
    decision: str
    notes: str = ""
    reviewer: str = ""
    scope: str = "fulltext"
    cohort: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────────

_DATABASE_INIT_LOCK = threading.Lock()
_INITIALIZED_DATABASE_PATHS: set[str] = set()


def _ensure_database_initialized(database: DatabaseClient) -> None:
    """Run expensive schema/data migrations once per WebUI database path."""
    database_key = str(Path(DB_PATH).resolve())
    if database_key in _INITIALIZED_DATABASE_PATHS:
        return
    with _DATABASE_INIT_LOCK:
        if database_key in _INITIALIZED_DATABASE_PATHS:
            return
        database.init_db_papers()
        _INITIALIZED_DATABASE_PATHS.add(database_key)


def _review_queue_url(**overrides) -> str:
    """Build an internal review queue URL from validated filter values."""
    parameters = {
        key: value for key, value in overrides.items()
        if value not in (None, "", False)
    }
    query = urlencode(parameters)
    return f"/relevance-review?{query}" if query else "/relevance-review"


def _safe_review_return_url(return_to: str, fallback: str) -> str:
    """Accept only a local relevance-review queue URL for back navigation."""
    if not return_to:
        return fallback
    parsed = urlsplit(return_to)
    if (
        not parsed.scheme
        and not parsed.netloc
        and parsed.path == "/relevance-review"
    ):
        return return_to
    return fallback


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
    """Build pipeline status dict for Dashboard API."""
    db = DatabaseClient(DB_PATH)
    try:
        _ensure_database_initialized(db)
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
        # Only full-text-adjudicated papers with complete summaries are reportable.
        pending_report = db.conn.execute(
            f"""
            {LATEST_RELEVANCE_REVIEW_CTE}
            SELECT COUNT(*)
            FROM papers AS p
            LEFT JOIN latest_relevance_review
              ON latest_relevance_review.doi = p.doi
            WHERE p.llm_summary_status = 'success'
              AND p.report_date IS NULL
              AND p.llm_relevance_status = 'success'
              AND {EFFECTIVE_RELEVANCE_CATEGORY_SQL} IN ('A', 'B')
              AND p.llm_relevance_basis = 'fulltext'
            """
        ).fetchone()[0]
        return {
            "total": total,
            "phases": phases,
            "pending_report": pending_report,
        }
    finally:
        db.conn.close()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root_redirect():
    """重定向到 Dashboard（Home 页面已删除）。"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    status_data = _pipeline_status()
    publishers = load_publishers()
    return templates.TemplateResponse(
        request, "dashboard.html", {
            "publisher_count": len(publishers),
            "initial_status": status_data,
        }
    )


@app.get("/pipeline/status")
async def pipeline_status_api():
    return JSONResponse(_pipeline_status())


@app.get("/pipeline/weekly-stats")
async def pipeline_weekly_stats():
    """Return per-day stats for the last 7 days: 3 buckets matching explained.html.j2.

    Buckets:
      - reportable:    final A/B with summary or abstract fallback, unreported
      - total_failed:  publisher/mineru/summary any failed
      - other:         total - reportable - total_failed (pending / skipped / reported)
    """
    db = DatabaseClient(DB_PATH)
    try:
        _ensure_database_initialized(db)
        today = datetime.now()
        days = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            days.append({
                "date": d.strftime("%Y%m%d"),
                "weekday": d.strftime("%a"),
                "total": 0,
                "reportable": 0,
                "publisher_failed": 0,
                "mineru_failed": 0,
                "summary_failed": 0,
                "total_failed": 0,
            })

        day_start = days[0]["date"]
        day_end = days[-1]["date"]
        rows = db.conn.execute(f"""
            {LATEST_RELEVANCE_REVIEW_CTE}
            SELECT
              p.created_date AS day,
              COUNT(*) AS total,
              SUM(CASE WHEN p.llm_summary_status = 'success'
                             AND p.report_date IS NULL
                             AND p.llm_relevance_status = 'success'
                             AND {EFFECTIVE_RELEVANCE_CATEGORY_SQL} IN ('A', 'B')
                             AND p.llm_relevance_basis = 'fulltext'
                       THEN 1 ELSE 0 END) AS reportable,
              SUM(CASE WHEN p.publisher_page_fetched_status = 'failed'
                       THEN 1 ELSE 0 END) AS publisher_failed,
              SUM(CASE WHEN p.mineru_parse_status = 'failed'
                       THEN 1 ELSE 0 END) AS mineru_failed,
              SUM(CASE WHEN p.llm_summary_status = 'failed'
                       THEN 1 ELSE 0 END) AS summary_failed,
              SUM(CASE WHEN p.publisher_page_fetched_status = 'failed'
                        OR p.mineru_parse_status = 'failed'
                        OR p.llm_summary_status = 'failed'
                       THEN 1 ELSE 0 END) AS total_failed
            FROM papers AS p
            LEFT JOIN latest_relevance_review
              ON latest_relevance_review.doi = p.doi
            WHERE p.created_date >= ? AND p.created_date <= ?
            GROUP BY p.created_date
            ORDER BY p.created_date
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
        _ensure_database_initialized(db)
        sort_by = sort if sort in ("created", "published", "summary") else "created"
        category_filter = category if category in ("a", "b", "ab", "all") else "ab"
        per_page = per_page if per_page in (50, 100, 200) else 100
        page = page if page >= 1 else 1
        offset = (page - 1) * per_page
        papers = db.get_papers(
            limit=per_page,
            offset=offset,
            sort_by=sort_by,
            category_filter=category_filter,
            has_summary=has_summary,
        )
        total_count = db.get_papers_count(
            category_filter=category_filter,
            has_summary=has_summary,
        )
    finally:
        db.conn.close()
    return templates.TemplateResponse(request, "papers.html", {
        "papers": papers, "sort_by": sort_by, "category_filter": category_filter,
        "has_summary_filter": has_summary,
        "page": page, "per_page": per_page, "total_count": total_count,
    })


# ── Manual relevance review ──────────────────────────────────────────────────

def _resolve_mineru_fulltext(output_dir: str):
    """Resolve a stored MinerU directory to its safe ``full.md`` path.

    Parameters
    ----------
    output_dir : str
        Relative output directory stored in the papers table.

    Returns
    -------
    Path or None
        Full-text path when it remains inside ``DATA_DIR`` and exists.
    """
    if not output_dir:
        return None
    candidate = (DATA_DIR / output_dir / "full.md").resolve()
    if not _is_report_path_in_directory(candidate, DATA_DIR):
        return None
    if not candidate.is_file():
        return None
    return candidate


@app.get("/relevance-review", response_class=HTMLResponse)
async def relevance_review_page(
    request: Request,
    status: str = "pending",
    category: str = "all",
    confidence: str = "all",
    disagreement: bool = False,
    search: str = "",
    sort: str = "priority",
    page: int = 1,
    per_page: int = 50,
    scope: str = "fulltext",
    cohort: str = "",
):
    """Render the manual relevance review queue."""
    page = max(1, page)
    per_page = per_page if per_page in (50, 100, 200) else 50
    sort_by = sort if sort in ("priority", "summary") else "priority"
    review_scope = scope if scope in ("fulltext", "screen-audit") else "fulltext"
    offset = (page - 1) * per_page
    with DatabaseClient(DB_PATH) as db:
        _ensure_database_initialized(db)
        audit_cohorts = db.get_relevance_audit_cohorts()
        cohort_names = {row["cohort"] for row in audit_cohorts}
        selected_cohort = cohort if cohort in cohort_names else (
            audit_cohorts[0]["cohort"] if audit_cohorts else ""
        )
        if review_scope == "screen-audit" and selected_cohort:
            papers = db.get_relevance_audit_queue(
                selected_cohort, status_filter=status, search_text=search,
                limit=per_page, offset=offset,
            )
            total_count = db.count_relevance_audit_queue(
                selected_cohort, status_filter=status, search_text=search,
            )
            pending_count = db.count_relevance_audit_queue(
                selected_cohort, status_filter="pending",
            )
            reviewed_count = db.count_relevance_audit_queue(
                selected_cohort, status_filter="reviewed",
            )
        elif review_scope == "screen-audit":
            papers = []
            total_count = pending_count = reviewed_count = 0
        else:
            papers = db.get_relevance_review_queue(
                status_filter=status,
                category_filter=category,
                confidence_filter=confidence,
                disagreement_only=disagreement,
                search_text=search,
                sort_by=sort_by,
                limit=per_page,
                offset=offset,
            )
            total_count = db.count_relevance_review_queue(
                status_filter=status,
                category_filter=category,
                confidence_filter=confidence,
                disagreement_only=disagreement,
                search_text=search,
            )
            pending_count = db.count_relevance_review_queue(
                status_filter="pending",
            )
            reviewed_count = db.count_relevance_review_queue(
                status_filter="reviewed",
            )
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    current_queue_url = _review_queue_url(
        scope=review_scope,
        cohort=selected_cohort if review_scope == "screen-audit" else "",
        status=status,
        category=category,
        confidence=confidence,
        disagreement=disagreement,
        search=search,
        sort=sort_by,
        page=min(page, total_pages),
        per_page=per_page,
    )
    scope_parameters = {
        "status": status,
        "category": category,
        "confidence": confidence,
        "disagreement": disagreement,
        "search": search,
        "sort": sort_by,
        "per_page": per_page,
    }
    fulltext_scope_url = _review_queue_url(
        scope="fulltext", **scope_parameters,
    )
    audit_scope_url = _review_queue_url(
        scope="screen-audit", cohort=selected_cohort, **scope_parameters,
    )
    detail_urls = {
        paper["doi"]: (
            f"/relevance-review/{quote(paper['doi'], safe='/')}?"
            + urlencode({
                "scope": review_scope,
                "cohort": selected_cohort,
                "return_to": current_queue_url,
            })
        )
        for paper in papers
    }
    random_url = "/relevance-review/random?" + urlencode({
        "scope": review_scope,
        "cohort": selected_cohort,
        "return_to": current_queue_url,
    })
    reset_filters_url = _review_queue_url(
        scope=review_scope,
        cohort=selected_cohort if review_scope == "screen-audit" else "",
    )
    has_active_filters = any((
        status != "pending",
        category != "all",
        confidence != "all",
        disagreement,
        bool(search),
        sort_by != "priority",
        per_page != 50,
    ))
    return templates.TemplateResponse(request, "relevance_review.html", {
        "papers": papers,
        "status_filter": status,
        "category_filter": category,
        "confidence_filter": confidence,
        "disagreement_only": disagreement,
        "search_text": search,
        "sort_by": sort_by,
        "page": min(page, total_pages),
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "pending_count": pending_count,
        "reviewed_count": reviewed_count,
        "review_scope": review_scope,
        "audit_cohorts": audit_cohorts,
        "selected_cohort": selected_cohort,
        "detail_urls": detail_urls,
        "random_url": random_url,
        "reset_filters_url": reset_filters_url,
        "has_active_filters": has_active_filters,
        "fulltext_scope_url": fulltext_scope_url,
        "audit_scope_url": audit_scope_url,
    })


@app.get("/relevance-review/random")
async def random_relevance_review(
    scope: str = "fulltext",
    cohort: str = "",
    return_to: str = "",
):
    """Redirect to a random pending item in the selected review scope."""
    review_scope = scope if scope in ("fulltext", "screen-audit") else "fulltext"
    with DatabaseClient(DB_PATH) as db:
        _ensure_database_initialized(db)
        if review_scope == "screen-audit":
            doi = db.get_random_relevance_audit_doi(cohort, pending_only=True)
        else:
            doi = db.get_random_relevance_review_doi(pending_only=True)
    fallback_url = _review_queue_url(scope=review_scope, cohort=cohort)
    queue_url = _safe_review_return_url(return_to, fallback_url)
    query = urlencode({
        "scope": review_scope,
        "cohort": cohort,
        "return_to": queue_url,
    })
    if not doi:
        return RedirectResponse(queue_url, status_code=303)
    encoded_doi = quote(doi, safe="/")
    return RedirectResponse(
        f"/relevance-review/{encoded_doi}?{query}", status_code=303,
    )


@app.get("/relevance-review/{doi:path}", response_class=HTMLResponse)
async def relevance_review_detail(
    request: Request,
    doi: str,
    scope: str = "fulltext",
    cohort: str = "",
    return_to: str = "",
):
    """Render one paper and its current manual review state."""
    review_scope = scope if scope in ("fulltext", "screen-audit") else "fulltext"
    with DatabaseClient(DB_PATH) as db:
        _ensure_database_initialized(db)
        if review_scope == "screen-audit":
            paper = db.get_relevance_audit_detail(cohort, doi)
        else:
            paper = db.get_relevance_review_detail(doi)
    if paper is None:
        return HTMLResponse("Paper not found", status_code=404)

    fallback_url = _review_queue_url(scope=review_scope, cohort=cohort)
    queue_url = _safe_review_return_url(return_to, fallback_url)
    random_url = "/relevance-review/random?" + urlencode({
        "scope": review_scope,
        "cohort": cohort,
        "return_to": queue_url,
    })

    fulltext = ""
    fulltext_path = None
    if review_scope == "fulltext":
        fulltext_path = _resolve_mineru_fulltext(paper["mineru_output_dir"])
    if fulltext_path:
        try:
            # Keep the detail page responsive while retaining enough context
            # for manual adjudication. The complete file remains on disk.
            fulltext = fulltext_path.read_text(encoding="utf-8")[:200000]
        except (OSError, UnicodeError) as error:
            logger.warning("Cannot read review full text %s: %s", doi, error)

    return templates.TemplateResponse(request, "relevance_review_detail.html", {
        "paper": paper,
        "fulltext": fulltext,
        "fulltext_available": bool(fulltext),
        "review_scope": review_scope,
        "audit_cohort": cohort,
        "queue_url": queue_url,
        "random_url": random_url,
    })


@app.post("/api/relevance-reviews")
async def save_relevance_review(payload: RelevanceReviewPayload):
    """Append a manual relevance review without changing LLM columns."""
    if not payload.doi.strip():
        return JSONResponse({"error": "DOI is required"}, status_code=422)
    if len(payload.notes) > 20000:
        return JSONResponse({"error": "Notes are too long"}, status_code=422)
    if len(payload.reviewer) > 200:
        return JSONResponse({"error": "Reviewer name is too long"}, status_code=422)
    if payload.scope not in {"fulltext", "screen-audit"}:
        return JSONResponse({"error": "Invalid review scope"}, status_code=422)
    if payload.scope == "screen-audit" and not payload.cohort.strip():
        return JSONResponse({"error": "Audit cohort is required"}, status_code=422)
    try:
        with DatabaseClient(DB_PATH) as db:
            _ensure_database_initialized(db)
            if payload.scope == "screen-audit":
                review_id = db.save_relevance_audit_review(
                    payload.cohort, payload.doi, payload.decision,
                    payload.notes, payload.reviewer,
                )
            else:
                review_id = db.save_relevance_review(
                    payload.doi, payload.decision, payload.notes,
                    payload.reviewer,
                )
    except DataBaseDOINotExists:
        return JSONResponse({"error": "Paper not found"}, status_code=404)
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    return JSONResponse({"ok": True, "review_id": review_id})


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


def _is_report_path_in_directory(file_path: Path, directory: Path) -> bool:
    """Return whether a resolved report path is contained by a report directory.

    Parameters
    ----------
    file_path : Path
        Candidate path, which may contain traversal components.
    directory : Path
        Directory that exclusively owns report files.
    """
    try:
        file_path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


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
        if not _is_report_path_in_directory(file_path, directory):
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
        if not _is_report_path_in_directory(file_path, directory):
            return JSONResponse({"error": "Invalid path"}, status_code=400)
        if file_path.exists():
            return FileResponse(str(file_path), filename=filename, media_type="text/markdown")
    return JSONResponse({"error": "File not found"}, status_code=404)
