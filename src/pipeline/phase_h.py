"""
Phase H: Email delivery.
"""

from datetime import datetime
from pathlib import Path

from config import SKIP_PHASE_H, load_email_config
from pipeline.base import logger
from processors.email_sender import EmailSender


def phase_h_email(report_dir):
    """Send latest report via email.

    Parameters
    ----------
    report_dir : Path
        Directory containing generated reports.
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

    report_dir = Path(report_dir)
    md_files = sorted(report_dir.glob("report_*.md"), reverse=True)

    attachments = []
    if md_files:
        attachments.append(str(md_files[0]))

    if not attachments:
        logger.info("Phase H: no report files, skipping")
        return

    sender = EmailSender(
        smtp_host=email_cfg["smtp_host"],
        smtp_port=email_cfg["smtp_port"],
        username=username,
        password=password,
        from_addr=email_cfg["from_addr"],
        to_addrs=to_addrs,
        use_tls=email_cfg.get("use_tls", True),
    )

    subject = f"PapersCrawler Report - {datetime.now().strftime('%Y-%m-%d')}"
    body = (
        f"您好，\n\n"
        f"以下是近期的文献追踪报告，包含 {len(attachments)} 个附件。\n\n"
        f"祝好！\nPapersCrawler 自动发送"
    )

    try:
        sender.send(subject, body, body_type="plain", attachments=attachments)
        logger.info(f"Email sent to {len(to_addrs)} recipients")
    except Exception as e:
        logger.error(f"Email send failed: {e}")

    logger.info("Phase H done")
