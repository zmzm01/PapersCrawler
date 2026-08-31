"""ntfy publishing and pipeline run summary formatting."""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.header import Header
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ntfy documents a 4096-byte message limit. Keep room for UTF-8 and the
# truncation marker so that the request remains safely below that limit.
MAX_NTFY_MESSAGE_BYTES = 3500
_LOG_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(?P<level>WARNING|ERROR|CRITICAL)\] "
    r"(?P<logger>[^:]+): (?P<message>.*)$"
)
_LOG_FILE_PATTERN = re.compile(
    r"^PaperCrawler-(?P<date>\d{4}-\d{2}-\d{2})\.log(?:\.\d+)?$"
)
_FAILURE_WORDS = (
    "failed", "failure", "crash", "error", "exception", "timeout", "timed out",
    "blocked", "request", "bot detection", "bot block", "失败", "错误", "异常",
    "超时", "阻塞",
)


def truncate_utf8(text: str, max_bytes: int = MAX_NTFY_MESSAGE_BYTES) -> str:
    """Truncate text at a UTF-8 character boundary.

    Parameters
    ----------
    text : str
        Text to truncate.
    max_bytes : int
        Maximum encoded byte length.

    Returns
    -------
    str
        Original text or a safely truncated text with a short marker.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    marker = "\n\n_其余内容已截断，请查看本地日志。_"
    marker_bytes = marker.encode("utf-8")
    if len(marker_bytes) >= max_bytes:
        return encoded[:max_bytes].decode("utf-8", errors="ignore")
    return (encoded[:max_bytes - len(marker_bytes)].decode("utf-8", errors="ignore")
            + marker)


@dataclass
class NtfyNotifier:
    """Publish one final Markdown notification to an ntfy topic."""

    enabled: bool = False
    base_url: str = ""
    topic: str = ""
    token: str = ""
    timeout: float = 10
    title: str = "PapersCrawler 运行汇总"
    priority: str = "default"

    def send(self, message: str) -> bool:
        """Publish a Markdown message and return whether it was accepted.

        Notification failures are deliberately contained here. A temporary
        ntfy outage must never change the pipeline result or exit status.
        """
        if not self.enabled:
            logger.debug("ntfy notification disabled")
            return False
        if not self.base_url or not self.topic:
            logger.warning("ntfy enabled but NTFY_BASE_URL or NTFY_TOPIC is missing")
            return False

        url = f"{self.base_url.rstrip('/')}/{self.topic.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}" if self.token else "",
            # RFC 2047 keeps a Chinese configured title valid for HTTP clients
            # that do not permit raw non-ASCII header values.
            "Title": Header(self.title, "utf-8").encode(),
            "Priority": self.priority,
            "Markdown": "yes",
            "Content-Type": "text/markdown; charset=utf-8",
        }
        headers = {key: value for key, value in headers.items() if value}
        payload = truncate_utf8(message).encode("utf-8")
        try:
            response = requests.post(url, data=payload, headers=headers,
                                     timeout=self.timeout)
            response.raise_for_status()
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status is None:
                logger.warning("ntfy notification failed: %s", type(error).__name__)
            else:
                logger.warning("ntfy notification failed with HTTP %s", status)
            return False
        logger.info("ntfy final run summary sent")
        return True


def _phase_icon(status: str) -> str:
    """Return a client-compatible icon for a phase status."""
    return {
        "success": "✅",
        "failed": "❌",
        "skipped": "⏭️",
        "pending": "⏳",
    }.get(status, "❔")


def _redact(text: str, token: str = "") -> str:
    """Remove credentials, URLs, and local paths before text reaches ntfy."""
    if token:
        text = text.replace(token, "[redacted]")
    text = re.sub(r"Bearer\s+\S+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "sk-[redacted]", text)
    text = re.sub(r"\b(?:sk|tk)_[A-Za-z0-9_-]+", "[redacted]", text)
    text = re.sub(r"(?i)(api[_ -]?key|token|password)=\S+", r"\1=[redacted]", text)
    text = re.sub(r"https?://\S+", "[URL]", text)
    text = re.sub(r"(?<!\w)/(?:home|tmp|var|Users)/\S+", "[PATH]", text)
    return text


def _parse_log_file(path: Path) -> list[dict[str, str]]:
    """Read warning/error records from one daily log file."""
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _LOG_LINE_PATTERN.match(line)
        if match:
            events.append(match.groupdict())
    return events


def _log_paths(log_dir: Path, log_date: date) -> list[Path]:
    """Return the active and rotated log files for one date."""
    if not log_dir.exists():
        return []
    paths = []
    for path in log_dir.glob(f"PaperCrawler-{log_date.isoformat()}.log*"):
        if path.is_file() and _LOG_FILE_PATTERN.fullmatch(path.name):
            paths.append(path)
    return sorted(paths)


def _phase_for_event(logger_name: str, message: str) -> str:
    """Infer the pipeline phase responsible for a log event."""
    text = f"{logger_name} {message}".lower()
    phase_match = re.search(
        r"(?:pipeline\.phase_|phase\s+)"
        r"(a-rss|a-cr|e3|e2|a|b|c|e|f|g|h)",
        text,
    )
    if phase_match:
        return phase_match.group(1).upper()
    if "publisher" in text or "scrap" in text or "bot detection" in text:
        return "C"
    if "mineru" in text or "pdf" in text or "pandoc" in text:
        return "E2"
    if any(
        name in text
        for name in (
            "prompt_explainer", "report_explainer", "llm_summarize", "paper_report"
        )
    ):
        return "F"
    if "paper_relevance" in text:
        return "E/E3"
    if "ntfy" in text:
        return "通知"
    if "llm" in text or "deepseek" in text or "anthropic" in text:
        return "LLM"
    return "其他"


def _event_category(event: dict[str, str]) -> tuple[str, bool]:
    """Return a compact category and whether it looks actionable."""
    logger_name = event.get("logger", "")
    message = event.get("message", "")
    phase = _phase_for_event(logger_name, message)
    text = f"{logger_name} {message}".lower()
    actionable = event.get("level") in {"ERROR", "CRITICAL"} or any(
        word in text for word in _FAILURE_WORDS
    )
    if actionable:
        if phase == "C":
            category = "C 抓取失败"
        elif phase == "E2":
            category = "E2 PDF/MinerU失败"
        elif phase == "通知":
            category = "通知失败"
        elif phase == "LLM" or phase in {"E", "E3", "E/E3", "F"}:
            category = f"{phase} LLM失败" if phase != "LLM" else "LLM失败"
        elif phase == "其他":
            category = "其他问题"
        else:
            category = f"{phase} 阶段失败"
    else:
        category = f"{phase} 其他提示"
    return category, actionable


def _current_log_events(result, log_dir: Path | None) -> list[dict[str, str]]:
    """Collect warning/error records belonging to the current run."""
    events: list[dict[str, str]] = []
    if log_dir is not None:
        start = result.started_at
        end = result.finished_at
        log_date = start.date()
        while log_date <= end.date():
            for path in _log_paths(log_dir, log_date):
                for event in _parse_log_file(path):
                    timestamp = datetime.strptime(
                        event["timestamp"], "%Y-%m-%d %H:%M:%S",
                    )
                    if start <= timestamp <= end:
                        events.append(event)
            log_date += timedelta(days=1)

    for phase in result.phase_results:
        if phase.status == "failed":
            events.append({
                "level": "ERROR",
                "logger": f"pipeline.phase_{phase.name.lower()}",
                "message": phase.error or "phase failed",
            })
    for sample in result.metrics.get("error_samples", []):
        event = {
            "level": "ERROR",
            "logger": f"pipeline.phase_{sample.get('stage', 'unknown').lower()}",
            "message": sample.get("message", "database error"),
        }
        if sample.get("doi"):
            event["doi"] = sample["doi"]
        events.append(event)
    return events


def _mineru_failure_streaks(
    result,
    as_of: date,
    retention_days: int = 14,
) -> list[tuple[str, int]]:
    """Find same-DOI MinerU download failures on consecutive local dates."""
    failures_by_doi: dict[str, set[date]] = defaultdict(set)
    lower_bound = as_of - timedelta(days=retention_days - 1)
    for failure in result.metrics.get("mineru_download_failures", []):
        doi = str(failure.get("doi") or "").strip()
        if not doi:
            continue
        try:
            failure_date = date.fromisoformat(str(failure["local_date"]))
        except (KeyError, ValueError):
            continue
        if lower_bound <= failure_date <= as_of:
            failures_by_doi[doi].add(failure_date)

    streaks = []
    for doi, failure_dates in sorted(failures_by_doi.items()):
        if as_of not in failure_dates:
            continue
        streak = 0
        cursor = as_of
        while cursor in failure_dates:
            streak += 1
            cursor -= timedelta(days=1)
        if streak >= 2:
            streaks.append((doi, streak))
    return sorted(streaks, key=lambda item: (-item[1], item[0]))


def _format_status_counts(section: dict) -> str:
    """Render the four persisted status counters as inline code."""
    counts = section.get("status_counts", {})
    return " · ".join(
        f"`{label}` {counts.get(label, 0)}"
        for label in ("success", "failed", "skipped", "pending")
    )


def _format_category_counts(section: dict) -> str:
    """Render A/B/C/D relevance counters as inline code."""
    counts = section.get("category_counts", {})
    return " · ".join(
        f"`{label}` {counts.get(label, 0)}"
        for label in ("A", "B", "C", "D")
    )


def _compact_message(text: str, width: int = 240) -> str:
    """Make a log message readable without overflowing the Web App layout."""
    one_line = " ".join(text.splitlines()).strip()
    if len(one_line) <= width:
        return one_line
    return one_line[: width - 1] + "…"


def format_pipeline_summary(
    result,
    token: str = "",
    log_dir: Path | None = None,
) -> str:
    """Render a Web App-oriented Markdown summary with full run context.

    Parameters
    ----------
    result : PipelineRunResult
        Result returned by ``pipeline.runner``.
    token : str, optional
        Credential value to redact from error text.
    log_dir : Path, optional
        Date-separated log directory used to classify current warnings and
        calculate consecutive failure streaks.

    Returns
    -------
    str
        Markdown suitable for an ntfy POST body.
    """
    status = result.status
    icon = "✅" if status == "success" else "⚠️" if status == "partial" else "❌"
    started = result.started_at.strftime("%Y-%m-%d %H:%M:%S")
    finished = result.finished_at.strftime("%Y-%m-%d %H:%M:%S")
    duration = (result.finished_at - result.started_at).total_seconds()
    mode = result.mode

    current_events = _current_log_events(result, log_dir)
    category_counts = Counter()
    category_examples: dict[str, str] = {}
    category_actionable: dict[str, bool] = {}
    for event in current_events:
        category, actionable = _event_category(event)
        category_counts[category] += 1
        category_examples.setdefault(category, event.get("message", ""))
        category_actionable[category] = (
            category_actionable.get(category, False) or actionable
        )

    lines = [
        f"# {icon} PapersCrawler · {mode} 运行汇总",
        "",
        f"> **运行状态**：`{status}`",
        f"> **开始时间**：`{started}`",
        f"> **结束时间**：`{finished}`",
        f"> **总耗时**：`{duration:.1f}s`",
        "",
        "---",
        "",
        "## 🧩 阶段执行",
    ]
    if result.phase_results:
        for phase in result.phase_results:
            lines.append(
                f"- {_phase_icon(phase.status)} **{phase.name}** · "
                f"`{phase.status}` · `{phase.duration_seconds:.1f}s`"
            )
    else:
        lines.append("- ⏳ 尚未开始")

    metrics = result.metrics or {}
    screen = metrics.get("relevance_screen", {})
    final = metrics.get("final_relevance", {})
    summary = metrics.get("summary", {})
    lines.extend([
        "",
        "---",
        "",
        "## 🎯 相关性判断",
        "",
        "### E · 标题与摘要初筛",
        f"- **处理状态**：{_format_status_counts(screen)}",
        f"- **相关性分类**：{_format_category_counts(screen)}",
        "",
        "### E3 · 正文终审",
        f"- **处理状态**：{_format_status_counts(final)}",
        f"- **相关性分类**：{_format_category_counts(final)}",
        "",
        "---",
        "",
        "## 📝 总结",
        "",
        "### F · 结构化总结",
        f"- **处理状态**：{_format_status_counts(summary)}",
    ])

    if category_counts:
        lines.extend(["", "---", "", "## 🚨 问题与错误"])
        for category, count in category_counts.most_common(6):
            issue_icon = "❌" if category_actionable.get(category) else "⚠️"
            example = _compact_message(
                _redact(category_examples[category], token), 180
            )
            lines.extend([
                "",
                f"### {issue_icon} {category} · `{count}` 条",
                f"> **示例**：{example or '未提供详情'}",
            ])
        omitted = len(category_counts) - min(len(category_counts), 6)
        if omitted:
            lines.extend(["", f"> 其余 `{omitted}` 类问题已省略。"])
    else:
        lines.extend([
            "",
            "---",
            "",
            "## ✅ 问题与错误",
            "",
            "> 本次运行没有记录到 WARNING 或 ERROR。",
        ])

    streaks = _mineru_failure_streaks(result, result.started_at.date())
    if streaks:
        lines.extend(["", "---", "", "## 🔁 连续失败提醒"])
        for doi, days in streaks[:4]:
            action = "需人工干预" if days >= 3 else "请关注"
            lines.append(
                f"- **E2 MinerU/PDF** · `{_compact_message(doi, 90)}` · "
                f"连续 **{days} 天** · **{action}**"
            )

    if category_examples and not any(
        event.get("level") == "ERROR" for event in current_events
    ):
        lines.extend([
            "",
            "> 详细日志：`python tools/log_report.py`",
        ])

    return truncate_utf8("\n".join(lines))
