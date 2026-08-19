#!/usr/bin/env python
"""
统一流水线 CLI 入口。

替代分散的 tools/schedule_daily.py / tools/schedule_weekly.py / src/main.py。

调用模式::

    # 每日调度（Phase A-RSS/A-CR/B/C/E/E2/E3/F）
    python tools/run_pipeline.py --daily

    # 每周调度（Phase G/H）
    python tools/run_pipeline.py --weekly

    # 全流程强制（包含 SKIP 的阶段）
    python tools/run_pipeline.py --all

    # 选定阶段（逗号分隔）
    python tools/run_pipeline.py --phases A-RSS,B,C,F

    # 默认（等效 --all）
    python tools/run_pipeline.py

    # 干跑预览（不实际执行）
    python tools/run_pipeline.py --daily --dry-run

典型 cron 配置::

    # 每天 2:00 每日运行
    0 2 * * * cd /path/to/PapersCrawler && python tools/run_pipeline.py --daily

    # 每周日 20:00（Asia/Shanghai）报告生成 + 邮件
    0 20 * * 7 cd /path/to/PapersCrawler && python tools/run_pipeline.py --weekly

无图形界面服务器需配合 xvfb-run（Phase C 需要虚拟显示器）::

    0 2 * * * cd /path/to/PapersCrawler && xvfb-run -a python tools/run_pipeline.py --daily

参数 ``--reset-publisher`` / ``--reset-mineru`` / ``--reset-relevance`` 控制是否在运行前
自动重置失败的 Publisher 抓取、MinerU 解析和 LLM 相关性判断（默认均开启）。
"""

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import CFG, LOG_FILE_PATH, DATA_DIR, DB_PATH, _check_mineru_token  # noqa: E402
from db.database import DatabaseClient  # noqa: E402
from pipeline.runner import (  # noqa: E402
    PipelineRunResult,
    run_daily,
    run_weekly,
    run_pipeline,
    run_phases,
    DAILY_PHASES,
    WEEKLY_PHASES,
    _PHASE_KEY_MAP,
)
from processors.ntfy_notifier import (  # noqa: E402
    NtfyNotifier,
    format_pipeline_summary,
)

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns
    -------
    argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="PaperCrawler 流水线统一入口 —— 替代 schedule_daily/schedule_weekly/main.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s --daily          每日调度 (A-RSS/A-CR/B/C/E/E2/E3/F)\n"
            "  %(prog)s --weekly         每周调度 (G/H)\n"
            "  %(prog)s --all            全流程强制（含 SKIP 阶段）\n"
            "  %(prog)s --phases A,B     仅执行 Phase A、B\n"
            "  %(prog)s --daily --dry-run 干跑预览\n"
        ),
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--daily",
        action="store_true",
        help="每日调度：Phase A-RSS/A-CR/B/C/E/E2/E3/F（默认尊重 SKIP_PHASE_* 配置）",
    )
    mode.add_argument(
        "--weekly",
        action="store_true",
        help="每周调度：Phase G/H（默认尊重 SKIP_PHASE_* 配置）",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="全流程强制：忽略 SKIP_PHASE_* 配置，执行全部阶段",
    )
    mode.add_argument(
        "--phases",
        type=str,
        metavar="A,B,C",
        help="逗号分隔的阶段列表，如 'A-RSS,B,C,F'",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式：仅打印执行计划，不实际运行",
    )
    parser.add_argument(
        "--reset-publisher",
        action="store_true",
        default=True,
        dest="reset_publisher",
        help="运行前重置失败的 Publisher 抓取（默认开启）",
    )
    parser.add_argument(
        "--no-reset-publisher",
        action="store_false",
        dest="reset_publisher",
        help="不重置失败的 Publisher 抓取",
    )
    parser.add_argument(
        "--reset-mineru",
        action="store_true",
        default=True,
        dest="reset_mineru",
        help="运行前重置失败的 MinerU 解析（默认开启）",
    )
    parser.add_argument(
        "--no-reset-mineru",
        action="store_false",
        dest="reset_mineru",
        help="不重置失败的 MinerU 解析",
    )
    parser.add_argument(
        "--reset-relevance",
        action="store_true",
        default=True,
        dest="reset_relevance",
        help="运行前重置失败的 LLM 相关性判断（默认开启）",
    )
    parser.add_argument(
        "--no-reset-relevance",
        action="store_false",
        dest="reset_relevance",
        help="不重置失败的 LLM 相关性判断",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=os.getenv("LOG_LEVEL", "DEBUG"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认从环境变量 LOG_LEVEL 读取，未设置则为 DEBUG）",
    )

    return parser


def _setup_logging(log_level: str) -> None:
    """配置日志系统：RotatingFileHandler + StreamHandler。

    Parameters
    ----------
    log_level : str
        日志级别（DEBUG / INFO / WARNING / ERROR）。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        LOG_FILE_PATH, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    console_handler = logging.StreamHandler()
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.DEBUG),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[file_handler, console_handler],
    )


def _run_auto_reset(reset_publisher: bool, reset_mineru: bool, reset_relevance: bool, dry_run: bool) -> None:
    """自动重置失败的论文状态，使其重新进入待处理队列。

    Parameters
    ----------
    reset_publisher : bool
        是否重置失败的 Publisher 抓取。
    reset_mineru : bool
        是否重置失败的 MinerU 解析。
    reset_relevance : bool
        是否重置失败的 LLM 相关性判断。
    dry_run : bool
        干跑模式不实际执行。
    """
    if dry_run:
        logger.info(
            "Would reset: publisher=%s, mineru=%s, relevance=%s",
            reset_publisher, reset_mineru, reset_relevance,
        )
        return

    reset_db = DatabaseClient(DB_PATH)
    reset_db.init_db_papers()

    if reset_publisher:
        count = reset_db.batch_reset_status(
            [("publisher_page_fetched_status", "pending")],
            "publisher_page_fetched_status = 'failed'",
        )
        if count:
            logger.info("Auto-reset %d failed publisher pages for retry", count)
    else:
        logger.info("Auto-reset publisher: disabled")

    if reset_mineru:
        count = reset_db.batch_reset_status(
            [("mineru_parse_status", "pending")],
            "mineru_parse_status IN ('failed', 'skipped')",
        )
        if count:
            logger.info("Auto-reset %d failed/skipped mineru parses for retry", count)
    else:
        logger.info("Auto-reset mineru: disabled")

    if reset_relevance:
        screen_count = reset_db.batch_reset_status(
            [("relevance_screen_status", "pending"),
             ("relevance_screen_error", None)],
            "relevance_screen_status = 'failed'",
        )
        final_count = reset_db.batch_reset_status(
            [("llm_relevance_status", "pending"),
             ("llm_relevance_error", None)],
            "llm_relevance_status = 'failed'",
        )
        if screen_count or final_count:
            logger.info(
                "Auto-reset relevance for retry: screen=%d, final=%d",
                screen_count, final_count,
            )
    else:
        logger.info("Auto-reset relevance: disabled")


def _dry_run_summary(phase_list, force, reset_publisher, reset_mineru, reset_relevance):
    """打印干跑模式摘要。

    Parameters
    ----------
    phase_list : list of str
        将执行的阶段列表。
    force : bool
        是否强制执行全部阶段。
    reset_publisher : bool
    reset_mineru : bool
    reset_relevance : bool
    """
    logger.info("Would run phases: %s", phase_list)

    effective_skip = {
        key: getattr(CFG, _PHASE_KEY_MAP[key], False) for key in _PHASE_KEY_MAP
    }
    logger.info("Effective skip: %s", effective_skip)
    logger.info("Force mode: %s", force)

    logger.info(
        "Would reset: publisher=%s, mineru=%s, relevance=%s",
        reset_publisher, reset_mineru, reset_relevance,
    )


def _send_final_notification(result: PipelineRunResult) -> None:
    """Send exactly one final Markdown summary when ntfy is enabled."""
    if not CFG.NTFY_ENABLED:
        logger.debug("ntfy final summary is disabled")
        return
    if not isinstance(result, PipelineRunResult):
        logger.warning("Skipping ntfy summary: pipeline returned no run result")
        return
    notifier = NtfyNotifier(
        enabled=CFG.NTFY_ENABLED,
        base_url=CFG.NTFY_BASE_URL,
        topic=CFG.NTFY_TOPIC,
        token=CFG.NTFY_TOKEN,
        timeout=CFG.NTFY_TIMEOUT,
        title=CFG.NTFY_TITLE,
        priority=CFG.NTFY_PRIORITY,
    )
    message = format_pipeline_summary(result, token=CFG.NTFY_TOKEN)
    notifier.send(message)


def main(argv=None) -> None:
    """CLI 入口：解析参数并执行对应的流水线操作。

    Parameters
    ----------
    argv : list of str, optional
        命令行参数列表。为 None 时从 sys.argv 读取。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # 日志配置必须在首次 logging 调用前完成
    _setup_logging(args.log_level)

    # logging 配置完成后再检测 token，避免 warning 偷装默认 handler
    _check_mineru_token()

    # 确定模式与阶段列表
    force = False
    phase_list = None

    if args.phases is not None:
        # 逗号分隔，去空白，去空项
        phases = [p.strip() for p in args.phases.split(",") if p.strip()]
        if not phases:
            logger.warning("--phases 解析后为空列表，无事可做")
            return
        phase_list = phases
    elif args.daily:
        phase_list = DAILY_PHASES
    elif args.weekly:
        phase_list = WEEKLY_PHASES
    elif args.all:
        force = True
        # run_pipeline(force=True) 内部调用 run_phases(force=True)
    # 默认行为：--all
    else:
        force = True

    # 执行
    if args.dry_run:
        if args.phases is not None:
            _dry_run_summary(phase_list, force, args.reset_publisher, args.reset_mineru, args.reset_relevance)
        elif args.all or (not args.daily and not args.weekly and args.phases is None):
            # --all 或默认模式下使用 run_pipeline(force=True)
            logger.info("Would run: run_pipeline(force=True) — all phases")
            _dry_run_summary(
                list(_PHASE_KEY_MAP.keys()), True,
                args.reset_publisher, args.reset_mineru, args.reset_relevance,
            )
        elif args.daily:
            _dry_run_summary(DAILY_PHASES, False, args.reset_publisher, args.reset_mineru, args.reset_relevance)
        elif args.weekly:
            _dry_run_summary(WEEKLY_PHASES, False, args.reset_publisher, args.reset_mineru, args.reset_relevance)
        # 不调用 auto-reset
        logger.info("Dry-run mode — no changes were made")
        return

    result = None
    try:
        # 自动重置
        _run_auto_reset(
            args.reset_publisher, args.reset_mineru, args.reset_relevance,
            dry_run=False,
        )

        # 实际运行
        if args.daily:
            result = run_daily()
        elif args.weekly:
            result = run_weekly()
        elif args.all:
            result = run_pipeline(force=True)
        elif args.phases is not None:
            result = run_phases(phase_list=phase_list, force=False)
        else:
            # 默认：全流程强制
            result = run_pipeline(force=True)
    except Exception as error:
        logger.error("Pipeline entrypoint crashed", exc_info=True)
        if args.daily:
            mode = "daily"
        elif args.weekly:
            mode = "weekly"
        else:
            mode = "custom"
        result = PipelineRunResult.failed_run(mode, error)
    finally:
        # A notifier outage is contained by NtfyNotifier. This is the only
        # notification call in the automatic execution path.
        if result is not None:
            _send_final_notification(result)


if __name__ == "__main__":
    main()
