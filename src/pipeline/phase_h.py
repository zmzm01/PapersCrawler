"""
Phase H: Email delivery.

Sends today's auto-generated report if it exists,
or a no-update notification if no report was generated.
"""

from datetime import datetime
from pathlib import Path

from config import SKIP_PHASE_H, load_email_config
from pipeline.base import logger
from processors.email_sender import EmailSender


def phase_h_email(auto_dir):
    """Send today's auto report or a no-update notification via email.

    Parameters
    ----------
    auto_dir : Path
        Directory containing auto-generated daily reports.
    """
    logger.info("--- Phase H: Email delivery ---")
    if SKIP_PHASE_H:
        logger.info("Phase H: SKIP_PHASE_H=True, skipping")
        return

    try:
        email_cfg = load_email_config()
    except Exception as e:
        logger.warning(f"Email config parse failed: {e}")
        return
    if not email_cfg:
        logger.info("Phase H: no email config, skipping")
        return

    username = email_cfg.get("username", "")
    password = email_cfg.get("password", "")
    if not username or not password or "@" not in username:
        logger.info("Phase H: email credentials not configured, skipping")
        return

    to_addrs = email_cfg.get("to_addrs", [])
    if not to_addrs:
        logger.info("Phase H: no recipients, skipping")
        return

    auto_dir = Path(auto_dir)
    today_str = datetime.now().strftime("%Y%m%d")
    today_report = auto_dir / f"report_{today_str}.md"

    sender = EmailSender(
        smtp_host=email_cfg["smtp_host"],
        smtp_port=email_cfg["smtp_port"],
        username=username,
        password=password,
        from_addr=email_cfg["from_addr"],
        to_addrs=to_addrs,
        use_tls=email_cfg.get("use_tls", True),
    )

    date_str = datetime.now().strftime("%Y-%m-%d")

    if today_report.exists():
        subject = f"PapersCrawler Report - {date_str}"
        body = (
            f"您好，\n\n"
            f"以下是近期的文献追踪报告。\n\n"
            f"祝好！\nPapersCrawler 自动发送"
        )
        try:
            sender.send(subject, body, body_type="plain", attachments=[str(today_report)])
            logger.info(f"Report sent: {today_report.name}")
        except Exception as e:
            logger.error(f"Email send failed: {e}")
    else:
        subject = f"PapersCrawler Report - {date_str} (No Updates)"
        body = (
            f"您好，\n\n"
            f"本期无新增相关论文，无需关注。\n\n"
            f"祝好！\nPapersCrawler 自动发送"
        )
        try:
            sender.send(subject, body, body_type="plain")
            logger.info("No new papers, sent no-update notification")
        except Exception as e:
            logger.error(f"Email send failed: {e}")

    logger.info("Phase H done")
