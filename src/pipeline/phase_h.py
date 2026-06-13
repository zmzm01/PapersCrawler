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
    CFG, EMAIL_TEMPLATE_DIR,
    load_email_config, load_publishers, load_keywords,
    build_scope_block,
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
    if CFG.SKIP_PHASE_H:
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

    # ── Gather template data: journals, keywords, publisher stats ──
    journal_list_html = ""
    keyword_list_html = ""
    publisher_stats_html = ""
    try:
        pubs = load_publishers()
        enabled_pubs = [j for j in pubs if j.get("enabled", True)]
        if enabled_pubs:
            items = "".join(
                f"<li>{j.get('name', j['id'])} ({j.get('publisher', '')})</li>"
                for j in enabled_pubs
            )
            journal_list_html = f"<ul style=\"margin:8px 0 0;padding-left:20px;color:#374151;font-size:14px;line-height:1.8;\">{items}</ul>"
    except Exception:
        pass
    try:
        kw_cfg = load_keywords()
        all_topics = []
        for sec in kw_cfg.get("scope_definition", {}).values():
            for t in sec.get("topics", []):
                kw = t.split("—")[0].strip() if "—" in t else t.strip()
                if kw:
                    all_topics.append(kw)
        if all_topics:
            items = "".join(
                f"<span style=\"display:inline-block;padding:2px 8px;margin:2px 4px;background:#eef2ff;color:#4338ca;border-radius:4px;font-size:12px;\">{kw}</span>"
                for kw in all_topics[:30]
            )
            keyword_list_html = f"<div style=\"margin:8px 0 0;line-height:2;\">{items}</div>"
            if len(all_topics) > 30:
                keyword_list_html += f"<p style=\"margin:4px 0 0;color:#9ca3af;font-size:12px;\">… 共 {len(all_topics)} 个关键词</p>"
    except Exception:
        pass
    # Full screening text block (for detailed template)
    domain_block_html = ""
    try:
        kw_cfg = load_keywords()
        scope = kw_cfg.get("scope_definition", {})
        irr = kw_cfg.get("irrelevant_fields", {})
        if scope:
            block_text = build_scope_block(scope, irr)
            block_text = (
                block_text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            domain_block_html = (
                f"<div style=\"margin:8px 0 0;padding:12px;background:#f1f5f9;"
                f"border-radius:4px;font-size:12px;line-height:1.6;"
                f"color:#374151;\">"
                f"<pre style=\"margin:0;white-space:pre-wrap;word-break:break-word;"
                f"max-height:400px;overflow-y:auto;font-family:inherit;\">"
                f"{block_text}</pre></div>"
                f"<p style=\"margin:12px 0 0;color:#64748b;font-size:13px;"
                f"line-height:1.5;font-style:italic;\">"
                f"💡 如果您对筛选关键词有任何改进建议，欢迎直接回复此邮件。</p>"
            )
    except Exception:
        pass
    try:
        # Build set of enabled publisher identifiers
        enabled_publishers = set()
        for j in (load_publishers() or []):
            if j.get("enabled", True):
                enabled_publishers.add(j.get("publisher", j["id"]))
        threshold = CFG.PUBLISHER_MAX_CONSECUTIVE_FAILURES  # default 3
        pub_stats = db.get_publisher_page_stats(days=7)
        if pub_stats:
            rows = ""
            for pub, s in sorted(pub_stats.items()):
                if enabled_publishers and pub not in enabled_publishers:
                    continue  # skip publishers without any enabled journal
                if s["failed"] >= threshold:
                    status_display = f"🚫 Blocked ({s['failed']} failures)"
                    status_color = "#dc2626"
                else:
                    status_display = f"✅ OK ({s['success']} successes)"
                    status_color = "#16a34a"
                rows += f"""<tr>
<td style="padding:6px 12px;border-bottom:1px solid #f3f4f6;color:#374151;font-size:13px;">{pub}</td>
<td style="padding:6px 12px;border-bottom:1px solid #f3f4f6;color:{status_color};font-size:13px;text-align:center;">{status_display}</td>
</tr>
"""
            publisher_stats_html = f"""<table style=\"width:100%;border-collapse:collapse;margin:8px 0 0;\">
<thead><tr>
<th style=\"padding:8px 12px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-size:12px;text-align:left;text-transform:uppercase;\">Publisher</th>
<th style=\"padding:8px 12px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-size:12px;text-align:center;text-transform:uppercase;\">Status (past 7 days)</th>
</tr></thead>
<tbody>{rows}</tbody></table>"""
    except Exception:
        pass

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
                        CFG.EMAIL_TEMPLATE_NAME,
                        report_title=f"PapersCrawler 文献追踪报告 — {date_str}",
                        paper_msg=paper_msg,
                        attachment_section=attachment_section,
                        journal_list=journal_list_html,
                        keyword_list=keyword_list_html,
                        domain_block=domain_block_html,
                        publisher_stats=publisher_stats_html,
                        threshold=str(threshold),
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
                        CFG.EMAIL_TEMPLATE_NAME,
                        report_title=f"PapersCrawler 文献追踪报告 — {date_str}（无新增）",
                        paper_msg=paper_msg,
                        attachment_section=attachment_section,
                        journal_list=journal_list_html,
                        keyword_list=keyword_list_html,
                        domain_block=domain_block_html,
                        publisher_stats=publisher_stats_html,
                        threshold=str(threshold),
                    ),
                    body_type="html",
            )
            logger.info("No new papers, sent no-update notification")
        except Exception as e:
            logger.error(f"Email send failed: {e}")

    logger.info("Phase H done")
