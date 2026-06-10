"""
Phase H: Email delivery.

Sends today's auto-generated report if it exists,
or a no-update notification if no report was generated.
Uses HTML email template from templates/email/<name>.html.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from config import (
    SKIP_PHASE_H, EMAIL_TEMPLATE_DIR, EMAIL_TEMPLATE_NAME, load_email_config,
)
from processors.email_sender import EmailSender
from db.database import DatabaseClient

logger = logging.getLogger(__name__)


def _render_email_template(template_name: str, **kwargs) -> str:
    """Load and render an HTML email template.

    Parameters
    ----------
    template_name : str
        Template filename stem (e.g. 'default' → templates/email/default.html).
    **kwargs
        Variables to substitute via str.format().

    Returns
    -------
    str
        Rendered HTML string. Falls back to plain text if template is missing.
    """
    path = EMAIL_TEMPLATE_DIR / f"{template_name}.html"
    if not path.exists():
        logger.warning(f"Email template not found: {path}, falling back")
        return kwargs.get("report_title", "")
    try:
        html = path.read_text(encoding="utf-8")
        return html.format(**kwargs)
    except (KeyError, ValueError) as e:
        logger.warning(f"Email template error {e}: {path}")
        return kwargs.get("report_title", "")


def phase_h_email(db, auto_dir, report_path=None):
    """Send today's auto report or a custom report via email.

    Recipients are read from the subscribers table in DB first,
    falling back to .env SMTP_TO_ADDRS if no subscribers are configured.
    Email body is rendered from the configured HTML template.

    Parameters
    ----------
    db : DatabaseClient
    auto_dir : Path
        Directory containing auto-generated daily reports.
    report_path : Path or None, optional
        Specific report file to send. If None, uses auto_dir/report_{today}.md.
        When provided, no "no updates" notification is sent — the file must exist.
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

    # 优先从 DB 订阅者表获取收件人，无订阅者时回退 .env 配置
    to_addrs = db.get_active_emails()
    if not to_addrs:
        to_addrs = email_cfg.get("to_addrs", [])
    if not to_addrs:
        logger.info("Phase H: no recipients (DB nor .env), skipping")
        return
    logger.info(f"Phase H: {len(to_addrs)} recipient(s) ({'DB subscribers' if db.get_active_emails() else '.env config'})")

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
    send_no_update = True

    # Determine which report file to send
    if report_path:
        report_path = Path(report_path)
        if not report_path.exists():
            logger.warning(f"Specified report not found: {report_path}")
            return
        logger.info(f"Sending custom report: {report_path.name}")
        send_no_update = False
    else:
        today_str = datetime.now().strftime("%Y%m%d")
        report_path = Path(auto_dir) / f"report_{today_str}.md"

    if report_path.exists():
        subject = f"PapersCrawler Report - {date_str}"
        # 从报告文件中统计论文数量（## 标题即为论文条目）
        report_text = report_path.read_text(encoding="utf-8")
        paper_count = str(len(re.findall(r'(?m)^## (?!目录)[^#]', report_text)))
        has_papers = True
        paper_msg = f"共收录 {paper_count} 篇相关论文，详细内容请参见附件报告。"
        attachment_section = """              <table role="presentation" style="width:100%;border-collapse:collapse;margin:24px 0;">
                <tr>
                  <td align="center" style="padding:16px;background-color:#f0fdf4;border-radius:6px;border:1px solid #bbf7d0;">
                    <span style="font-size:13px;color:#16a34a;font-weight:500;">📎 报告文件已随此邮件附上</span>
                  </td>
                </tr>
              </table>"""
        try:
            sender.send(
                subject,
                _render_email_template(
                    EMAIL_TEMPLATE_NAME,
                    report_title=f"PapersCrawler 文献追踪报告 — {date_str}",
                    paper_msg=paper_msg,
                    attachment_section=attachment_section,
                ),
                body_type="html",
                attachments=[str(report_path)],
            )
            logger.info(f"Report sent: {report_path.name}")
        except Exception as e:
            logger.error(f"Email send failed: {e}")
    elif send_no_update:
        subject = f"PapersCrawler Report - {date_str} (No Updates)"
        paper_msg = "本期无新增相关论文，无需关注。"
        attachment_section = ""
        try:
            sender.send(
                subject,
                _render_email_template(
                    EMAIL_TEMPLATE_NAME,
                    report_title=f"PapersCrawler 文献追踪报告 — {date_str}（无新增）",
                    paper_msg=paper_msg,
                    attachment_section=attachment_section,
                ),
                body_type="html",
            )
            logger.info("No new papers, sent no-update notification")
        except Exception as e:
            logger.error(f"Email send failed: {e}")

    logger.info("Phase H done")
