"""ntfy publishing and pipeline run summary formatting."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from email.header import Header
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

# ntfy documents a 4096-byte message limit. Keep room for UTF-8 and the
# truncation marker so that the request remains safely below that limit.
MAX_NTFY_MESSAGE_BYTES = 3500
MAX_ERROR_SAMPLES = 3
MAX_ERROR_MESSAGE_LENGTH = 180


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


def redact_error(error: object, secrets: Iterable[str] = ()) -> str:
    """Return a short, notification-safe error description.

    API keys, bearer values, URLs, and local paths are removed because error
    messages may originate in third-party clients and should not be sent to a
    push notification service.
    """
    text = str(error or "").replace("\n", " ").strip()
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(sk|tk)_[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"https?://\S+", "[URL]", text)
    text = re.sub(r"(?<!\w)/(?:home|tmp|var|Users)/\S+", "[PATH]", text)
    return text[:MAX_ERROR_MESSAGE_LENGTH] or "未提供错误详情"


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


def _status_counts(section: dict) -> str:
    """Format status counters from a run-metrics section."""
    counts = section.get("status_counts", {})
    return " · ".join(
        f"`{label}` {counts.get(label, 0)}"
        for label in ("success", "failed", "skipped", "pending")
    )


def _category_counts(section: dict) -> str:
    """Format A/B/C/D counters from a run-metrics section."""
    counts = section.get("category_counts", {})
    return " · ".join(f"`{label}` {counts.get(label, 0)}"
                     for label in ("A", "B", "C", "D"))


def _phase_icon(status: str) -> str:
    """Return a compact, client-compatible icon for a phase status."""
    return {
        "success": "✅",
        "failed": "❌",
        "skipped": "⏭️",
        "pending": "⏳",
    }.get(status, "❔")


def format_pipeline_summary(result, token: str = "") -> str:
    """Render one compact Markdown summary for a pipeline run.

    Parameters
    ----------
    result : PipelineRunResult
        Result returned by ``pipeline.runner``.
    token : str, optional
        ntfy token used only for defensive redaction of error text.

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

    lines = [
        f"## {icon} PapersCrawler · {mode} 运行汇总",
        "",
        f"> **状态**：`{status}`  ·  **总耗时**：`{duration:.1f}s`",
        f"> **开始**：{started}",
        f"> **结束**：{finished}",
        "",
        "---",
        "",
        "### 🧩 阶段执行",
    ]
    for phase in result.phase_results:
        lines.append(
            f"- {_phase_icon(phase.status)} **{phase.name}** · "
            f"`{phase.status}` · `{phase.duration_seconds:.1f}s`"
        )
    if not result.phase_results:
        lines.append("- ⏳ 尚未开始")

    metrics = result.metrics or {}
    screen = metrics.get("relevance_screen", {})
    final = metrics.get("final_relevance", {})
    summary = metrics.get("summary", {})
    lines.extend([
        "",
        "---",
        "",
        "### 🎯 相关性判断",
        f"- **E 初筛**：{_status_counts(screen)}",
        f"  - 分类：{_category_counts(screen)}",
        f"- **E3 正文终审**：{_status_counts(final)}",
        f"  - 分类：{_category_counts(final)}",
        "",
        "### 📝 总结",
        f"- **F 结构化总结**：{_status_counts(summary)}",
        "",
        "### 🚨 错误",
    ])

    errors = []
    errors.extend({"stage": "运行", "message": error}
                  for error in result.errors)
    errors.extend(metrics.get("error_samples", []))
    if errors:
        for error in errors[:MAX_ERROR_SAMPLES * 3]:
            message = redact_error(error.get("message", ""), [token])
            lines.append(f"- **{error.get('stage', '未知')}**：{message}")
        if len(errors) > MAX_ERROR_SAMPLES * 3:
            lines.append(f"- 其余 {len(errors) - MAX_ERROR_SAMPLES * 3} 条错误已省略")
    else:
        lines.append("- 无")
    return truncate_utf8("\n".join(lines))
