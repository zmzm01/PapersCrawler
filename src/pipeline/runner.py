"""
Pipeline orchestrator.

Provides run_pipeline() for full execution and run_phases() for selective runs.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime

from config import (
    CFG, load_publishers, load_keywords,
    DB_PATH, REPORT_DIR, AUTO_REPORT_DIR, USER_REPORT_DIR, DATA_DIR,
)

logger = logging.getLogger(__name__)


@dataclass
class PhaseRunResult:
    """Outcome and elapsed time for one pipeline phase."""

    name: str
    status: str
    duration_seconds: float
    error: str | None = None

    def as_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class PipelineRunResult:
    """Complete outcome of one pipeline invocation."""

    mode: str
    started_at: datetime
    finished_at: datetime
    phase_results: list[PhaseRunResult] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return success, partial, or failed based on recorded outcomes."""
        if not self.phase_results and self.errors:
            return "failed"
        failed = self.errors or [
            phase.error for phase in self.phase_results
            if phase.status == "failed" and phase.error
        ]
        if not failed:
            return "success"
        if any(phase.status == "success" for phase in self.phase_results):
            return "partial"
        return "failed"

    @classmethod
    def failed_run(cls, mode: str, error: object) -> "PipelineRunResult":
        """Create a result for an exception outside the runner."""
        now = datetime.now()
        return cls(mode=mode, started_at=now, finished_at=now,
                   errors=[str(error)])

    def as_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        data = asdict(self)
        data["status"] = self.status
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat()
        return data


# Phase short key → CFG attribute mapping used for effective-skip resolution.
_PHASE_KEY_MAP = {
    "A-RSS": "SKIP_PHASE_A_RSS", "A-CR": "SKIP_PHASE_A_CR",
    "B": "SKIP_PHASE_B", "C": "SKIP_PHASE_C",
    "E": "SKIP_PHASE_E", "E2": "SKIP_PHASE_E2", "E3": "SKIP_PHASE_E3",
    "F": "SKIP_PHASE_F", "G": "SKIP_PHASE_G", "H": "SKIP_PHASE_H",
}


from db.database import DatabaseClient

from pipeline.phase_a import phase_a_rss, phase_a_crossref
from pipeline.phase_b import phase_b_crossref
from pipeline.phase_c import phase_c_publisher
from pipeline.phase_e import phase_e_llm_relevance
from pipeline.phase_e2 import phase_e2_mineru
from pipeline.phase_e3 import phase_e3_fulltext_relevance
from pipeline.phase_f import phase_f_llm_summary
from pipeline.phase_g import phase_g_report
from pipeline.phase_h import phase_h_email


def run_phases(phase_list=None, force=False, mode="custom"):
    """Run selected phases of the pipeline.

    Parameters
    ----------
    phase_list : list of str, optional
        Phase names to run (e.g. ["A", "C", "F"]).
        If None, runs all non-skipped phases.
    force : bool, optional
        If True, run every phase regardless of SKIP_PHASE_* settings.
    mode : str, optional
        Human-readable invocation mode included in the final summary.
    """
    started_at = datetime.now()
    result = PipelineRunResult(mode=mode, started_at=started_at,
                               finished_at=started_at)
    db = None
    try:
        publishers = load_publishers()
        keywords = load_keywords()
        logger.info("Loaded %d publishers", len(publishers))
        logger.info("Scope definition: %d sub-domains",
                    len(keywords.get("scope_definition", {})))

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        AUTO_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        USER_REPORT_DIR.mkdir(parents=True, exist_ok=True)

        db = DatabaseClient(DB_PATH)
        db.init_db_papers()
        logger.info("Database ready: %s", DB_PATH)

        effective_skip = {
            key: getattr(CFG, _PHASE_KEY_MAP[key]) for key in _PHASE_KEY_MAP
        }
        phase_map = {
            "A-RSS": (phase_a_rss, [db, publishers, force], not effective_skip["A-RSS"]),
            "A-CR": (phase_a_crossref, [db, publishers, force], not effective_skip["A-CR"]),
            "B": (phase_b_crossref, [db], not effective_skip["B"]),
            "C": (phase_c_publisher, [db, publishers], not effective_skip["C"]),
            "E": (phase_e_llm_relevance, [db], not effective_skip["E"]),
            "E2": (phase_e2_mineru, [db], not effective_skip["E2"]),
            "E3": (phase_e3_fulltext_relevance, [db], not effective_skip["E3"]),
            "F": (phase_f_llm_summary, [db], not effective_skip["F"]),
            "G": (phase_g_report, [db, AUTO_REPORT_DIR, USER_REPORT_DIR], not effective_skip["G"]),
            "H": (phase_h_email, [db, AUTO_REPORT_DIR], not effective_skip["H"]),
        }

        if phase_list is None:
            if force:
                phase_list = list(phase_map.keys())
            else:
                phase_list = [k for k, (_, _, enabled) in phase_map.items() if enabled]

        for key in phase_list:
            phase_started = datetime.now()
            if key not in phase_map:
                error = f"Unknown phase: {key}"
                result.phase_results.append(PhaseRunResult(
                    key, "failed", 0.0, error,
                ))
                result.errors.append(error)
                continue
            func, args, enabled = phase_map[key]
            if not enabled:
                logger.info("Phase %s: skipped by config/override", key)
                result.phase_results.append(PhaseRunResult(
                    key, "skipped", 0.0, "disabled by configuration",
                ))
                continue
            try:
                func(*args)
            except Exception as error:
                logger.error("Phase %s crashed — continuing to next phase", key,
                             exc_info=True)
                result.phase_results.append(PhaseRunResult(
                    key, "failed", (datetime.now() - phase_started).total_seconds(),
                    str(error),
                ))
                result.errors.append(f"Phase {key}: {error}")
            else:
                result.phase_results.append(PhaseRunResult(
                    key, "success", (datetime.now() - phase_started).total_seconds(),
                ))

        try:
            result.metrics = db.get_run_metrics(started_at)
        except Exception as error:
            logger.error("Could not collect run metrics", exc_info=True)
            result.errors.append(f"统计: {error}")
    except Exception as error:
        logger.error("Pipeline setup crashed", exc_info=True)
        result.errors.append(f"初始化: {error}")
        result.phase_results.append(PhaseRunResult(
            "初始化", "failed", (datetime.now() - started_at).total_seconds(),
            str(error),
        ))
    finally:
        if db is not None:
            db.close()
        result.finished_at = datetime.now()
    logger.info("Pipeline finished with status: %s", result.status)
    return result

 
def run_pipeline(force=False, run_all=False):
    """Run the full pipeline (equivalent to old main()).

    Parameters
    ----------
    force : bool, optional
        Deprecated. Use ``run_all`` instead.
    run_all : bool, optional
        If True, run ALL phases regardless of SKIP_PHASE_* config.
    """
    return run_phases(force=force or run_all, mode="all")


# ── 便捷方法：每日/每周调度 ─────────────────────────────────────────

DAILY_PHASES = ["A-RSS", "A-CR", "B", "C", "E", "E2", "E3", "F"]
WEEKLY_PHASES = ["G", "H"]


def run_daily():
    """每日运行：发现 → LLM 总结。

    等价于依次执行 Phase A-RSS / A-CR / B / C / E / E2 / F。
    尊重 settings.yaml 中的 SKIP_PHASE_* 配置（CLI 模式，force=False）。

    典型 cron 用法:

        # 每天 2:00
        0 2 * * * cd /path/to/PapersCrawler && python tools/schedule_daily.py
    """
    return run_phases(phase_list=DAILY_PHASES, mode="daily")


def run_weekly():
    """每周运行：报告生成 → 邮件推送。

    等价于依次执行 Phase G / H。
    尊重 settings.yaml 中的 SKIP_PHASE_* 配置（CLI 模式，force=False）。

    典型 cron 用法:

        # 每周日 20:00（Asia/Shanghai）
        0 20 * * 7 cd /path/to/PapersCrawler && python tools/schedule_weekly.py
    """
    return run_phases(phase_list=WEEKLY_PHASES, mode="weekly")


if __name__ == "__main__":
    import sys
    phases = sys.argv[1:] if len(sys.argv) > 1 else None
    run_phases(phases)
