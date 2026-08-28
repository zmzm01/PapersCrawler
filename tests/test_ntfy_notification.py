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
                {
                    "stage": "E3", "doi": "10.1234/e3",
                    "message": "Authorization: Bearer sk-secret",
                },
                {
                    "stage": "C", "doi": "10.1234/c",
                    "message": "GET https://private.example/a failed",
                },
            ],
            "mineru_download_failures": [],
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
    """Summary uses the Web App Markdown layout without leaking credentials."""
    message = format_pipeline_summary(_result(), token="sk-secret")
    assert "partial" in message
    assert "1080.0s" in message
    assert "# ⚠️ PapersCrawler · daily 运行汇总" in message
    assert "> **运行状态**：`partial`" in message
    assert "## 🧩 阶段执行" in message
    assert "✅ **E** · `success` · `4.2s`" in message
    assert "❌ **E3** · `failed` · `8.1s`" in message
    assert "## 🎯 相关性判断" in message
    assert "### E · 标题与摘要初筛" in message
    assert "### E3 · 正文终审" in message
    assert "### F · 结构化总结" in message
    assert "### ❌ E3 LLM失败 · `2` 条" in message
    assert "### ❌ C 抓取失败 · `1` 条" in message
    assert "[redacted]" in message
    assert "sk-secret" not in message
    assert "private.example" not in message
    assert "[URL]" in message
    assert "| 阶段 | 结果 | 耗时 |" not in message
    assert len(message.encode("utf-8")) <= 3500
    assert len(truncate_utf8("论文" * 3000).encode("utf-8")) <= 3500


def test_summary_reports_warning_type_and_failure_streak(tmp_path):
    """Warnings are classified and same-DOI MinerU failures are flagged."""
    for log_date in ("2026-08-16", "2026-08-17", "2026-08-18"):
        path = tmp_path / f"PaperCrawler-{log_date}.log"
        path.write_text(
            f"{log_date} 02:10:00 [WARNING] pipeline.phase_c: "
            "Publisher request failed after retry\n"
            f"{log_date} 02:11:00 [WARNING] processors.prompt_explainer: "
            "scope definition is empty\n",
            encoding="utf-8",
        )

    result = _result()
    result.metrics["mineru_download_failures"] = [
        {"doi": "10.1234/mineru", "local_date": log_date, "error": "download failed"}
        for log_date in ("2026-08-16", "2026-08-17", "2026-08-18")
    ] + [
        {"doi": "10.1234/other", "local_date": log_date, "error": "download failed"}
        for log_date in ("2026-08-17", "2026-08-18")
    ]
    message = format_pipeline_summary(result, log_dir=tmp_path)

    assert "## 🚨 问题与错误" in message
    assert "### ❌ C 抓取失败 · `2` 条" in message
    assert "### ⚠️ F 其他提示 · `1` 条" in message
    assert "## 🔁 连续失败提醒" in message
    assert "**E2 MinerU/PDF** · `10.1234/mineru` · 连续 **3 天** · **需人工干预**" in message
    assert "**E2 MinerU/PDF** · `10.1234/other` · 连续 **2 天** · **请关注**" in message


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
