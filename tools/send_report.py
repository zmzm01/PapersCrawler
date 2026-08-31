#!/usr/bin/env python
"""
CLI 邮件发送工具 —— 通过 Phase H 发送指定报告。

用法示例::

    # 发送 auto/ 目录下的日报
    python tools/send_report.py --report report_20260726.md

    # 发送 user/ 目录下的自定义报告
    python tools/send_report.py --report report_20260726_120000.md

    # 覆盖收件人
    python tools/send_report.py --report report_20260726.md --recipients a@x.com,b@y.com

    # 干跑预览（不真正发送）
    python tools/send_report.py --report report_20260726.md --dry-run

    # 指定日志级别
    python tools/send_report.py --report report_20260726.md --log-level INFO

报告文件查找顺序：
    1. ``AUTO_REPORT_DIR``（``data/reports/auto/``）
    2. ``USER_REPORT_DIR``（``data/reports/user/``）

文件不存在时退出码为 2。
"""

import argparse
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from config import DATA_DIR, AUTO_REPORT_DIR, USER_REPORT_DIR  # noqa: E402
from pipeline.phase_h import phase_h_email  # noqa: E402
from config import load_email_recipients  # noqa: E402
from logging_config import configure_logging, resolve_log_dir  # noqa: E402

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns
    -------
    argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="PaperCrawler 邮件发送工具 —— 通过 Phase H 发送指定报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s --report report_20260726.md\n"
            "  %(prog)s --report report_20260726.md --recipients a@x.com,b@y.com\n"
            "  %(prog)s --report report_20260726.md --dry-run\n"
        ),
    )

    parser.add_argument(
        "--report",
        type=str,
        required=True,
        metavar="FILENAME",
        help="报告文件名（在 auto/ 或 user/ 目录中查找）",
    )
    parser.add_argument(
        "--recipients",
        type=str,
        default=None,
        metavar="a@x.com,b@y.com",
        help="收件人列表（逗号分隔），覆盖默认收件人配置",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式：仅打印发送计划，不实际发送",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认从环境变量 LOG_LEVEL 读取，未设置则为 INFO）",
    )

    return parser


def _setup_logging(log_level: str) -> None:
    """配置按日期分文件的日志系统。

    Parameters
    ----------
    log_level : str
        日志级别（DEBUG / INFO / WARNING / ERROR）。
    """
    configure_logging(
        log_level,
        resolve_log_dir(DATA_DIR / "logs"),
        default_level=logging.INFO,
    )


def _find_report_file(filename: str) -> Path | None:
    """在 AUTO_REPORT_DIR 和 USER_REPORT_DIR 中查找报告文件。

    Parameters
    ----------
    filename : str
        报告文件名（如 ``report_20260726.md``）。

    Returns
    -------
    Path or None
        找到的完整路径，未找到则返回 None。
    """
    for base_dir in (AUTO_REPORT_DIR, USER_REPORT_DIR):
        candidate = base_dir / filename
        if candidate.exists():
            return candidate.resolve()
    return None


def _parse_recipients(recipients_str: str) -> list[str]:
    """解析逗号分隔的收件人字符串，去空白并过滤空项。

    Parameters
    ----------
    recipients_str : str
        逗号分隔的邮箱地址字符串。

    Returns
    -------
    list of str
        收件人地址列表。
    """
    return [addr.strip() for addr in recipients_str.split(",") if addr.strip()]


def main(argv=None) -> None:
    """CLI 入口：解析参数并发送报告。

    Parameters
    ----------
    argv : list of str, optional
        命令行参数列表。为 None 时从 sys.argv 读取。

    Raises
    ------
    SystemExit
        报告文件不存在时退出码为 2。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # 日志配置
    _setup_logging(args.log_level)

    # 查找报告文件
    report_path = _find_report_file(args.report)
    if report_path is None:
        logger.error("Report not found: %s (searched auto/ and user/)", args.report)
        sys.exit(2)

    # 解析收件人
    if args.recipients:
        to_addrs = _parse_recipients(args.recipients)
    else:
        to_addrs = load_email_recipients()

    # 构建主题
    subject = f"PapersCrawler Report - {report_path.stem}"

    if args.dry_run:
        logger.info("Would send to %d recipient(s): %s", len(to_addrs), to_addrs)
        logger.info("Attachment: %s", report_path)
        logger.info("Subject: %s", subject)
        logger.info("Dry-run mode — no email was sent")
        return

    # 调用 Phase H 发送
    # phase_h_email 接受 db, auto_dir, report_path, to_addrs
    # 我们不需要 db 实例（已由 phase_h 内部管理），但签名需要
    # 使用 from db.database import DatabaseClient
    from db.database import DatabaseClient  # noqa: E402
    from config import DB_PATH  # noqa: E402

    db = DatabaseClient(DB_PATH)
    db.init_db_papers()

    phase_h_email(db, AUTO_REPORT_DIR, report_path=report_path, to_addrs=to_addrs)


if __name__ == "__main__":
    main()
