"""Offline tests for the single ntfy Markdown run summary."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from db.database import DatabaseClient, FetchStatus
from pipeline.runner import PipelineRunResult, PhaseRunResult
from processors.ntfy_notifier import (
    NtfyNotifier,
    format_pipeline_summary,
    truncate_utf8,
)


def _result():
    """Build a representative result without running external services."""
    now = datetime(2026, 8, 18, 2, 18)
    return PipelineRunResult(
        mode="daily",
        started_at=now - timedelta(minutes=18),
        finished_at=now,
        phase_results=[
            PhaseRunResult("E", "success", 4.2),
            PhaseRunResult("E3", "failed", 8.1, "LLM token sk-secret leaked"),
            PhaseRunResult("F", "success", 2.0),
        ],
        metrics={
            "relevance_screen": {
                "status_counts": {"success": 12, "failed": 1, "skipped": 0, "pending": 2},
                "category_counts": {"A": 3, "B": 4, "C": 2, "D": 3},
            },
            "final_relevance": {
                "status_counts": {"success": 6, "failed": 1, "skipped": 0, "pending": 1},
                "category_counts": {"A": 2, "B": 2, "C": 1, "D": 1},
            },
            "summary": {
                "status_counts": {"success": 4, "failed": 1, "skipped": 1, "pending": 0},
                "category_counts": {"A": 0, "B": 0, "C": 0, "D": 0},
            },
            "error_samples": [
                {"stage": "E3", "message": "Authorization: Bearer sk-secret"},
                {"stage": "C", "message": "GET https://private.example/a failed"},
            ],
        },
        errors=[],
    )


def test_ntfy_sends_one_markdown_request_without_public_link():
    """The request uses Markdown/Bearer headers and no click/dashboard link."""
    response = MagicMock()
    notifier = NtfyNotifier(
        enabled=True,
        base_url="https://ntfy.internal",
        topic="private_topic",
        token="tk_real_secret",
    )
    with patch("processors.ntfy_notifier.requests.post", return_value=response) as post:
        assert notifier.send("## summary") is True

    post.assert_called_once()
    url, kwargs = post.call_args.args[0], post.call_args.kwargs
    assert url == "https://ntfy.internal/private_topic"
    assert kwargs["headers"]["Authorization"] == "Bearer tk_real_secret"
    assert kwargs["headers"]["Markdown"] == "yes"
    assert kwargs["headers"]["Content-Type"].startswith("text/markdown")
    assert "Click" not in kwargs["headers"]
    assert b"## summary" == kwargs["data"]


def test_ntfy_failure_is_contained():
    """A request failure returns False and does not raise to the pipeline."""
    notifier = NtfyNotifier(enabled=True, base_url="https://ntfy.internal", topic="t")
    with patch(
        "processors.ntfy_notifier.requests.post",
        side_effect=__import__("requests").RequestException("offline"),
    ):
        assert notifier.send("summary") is False


def test_summary_is_redacted_and_conservatively_truncated():
    """Summary uses ntfy-compatible Markdown without tables or public links."""
    message = format_pipeline_summary(_result(), token="sk-secret")
    assert "相关性判断" in message
    assert "总结" in message
    assert "错误" in message
    assert "sk-secret" not in message
    assert "private.example" not in message
    assert "Dashboard" not in message
    assert "### 🧩 阶段执行" in message
    assert "✅ **E**" in message
    assert "| 阶段 | 结果 | 耗时 |" not in message
    assert len(message.encode("utf-8")) <= 3500
    assert len(truncate_utf8("论文" * 3000).encode("utf-8")) <= 3500


def test_metrics_are_limited_to_current_run(tmp_path):
    """E/E3/F counters exclude older database history."""
    db = DatabaseClient(tmp_path / "metrics.db")
    db.init_db_papers()
    db.insert_rss_basicinfo("10.0000/new", "New", "http://new", "J", "pub", "2026")
    db.insert_rss_basicinfo("10.0000/old", "Old", "http://old", "J", "pub", "2026")
    db.update_relevance_screen(
        "10.0000/new", "A", "[]", "high", "ok", FetchStatus.SUCCESS.value,
        "2026-08-18 02:01:00",
    )
    db.update_llm_relevance(
        "10.0000/new", "B", "[]", "high", "ok", FetchStatus.SUCCESS.value,
        "2026-08-18 02:02:00", basis="fulltext",
    )
    db.update_llm_summary(
        "10.0000/new", "{}", FetchStatus.SUCCESS.value,
        "2026-08-18 02:03:00",
    )
    db.update_relevance_screen(
        "10.0000/old", "D", "[]", "low", "old", FetchStatus.SUCCESS.value,
        "2026-08-17 23:59:00",
    )

    metrics = db.get_run_metrics("2026-08-18 02:00:00")
    assert metrics["relevance_screen"]["category_counts"] == {"A": 1, "B": 0, "C": 0, "D": 0}
    assert metrics["final_relevance"]["category_counts"] == {"A": 0, "B": 1, "C": 0, "D": 0}
    assert metrics["summary"]["status_counts"]["success"] == 1
    db.close()
