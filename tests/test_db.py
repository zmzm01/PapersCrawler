"""
测试: 数据库操作 (db.py)

覆盖范围:
  - 表创建 (init_db_papers)
  - DOI 存在性检查
  - RSS 基本信息插入与去重
  - 各阶段状态更新 (CrossRef, Publisher, Keyword, LLM)
  - 错误信息记录
  - 查询方法 (get_pendings, get_relevant_papers, get_papers_with_summary)

所有测试使用临时 SQLite 数据库，不污染真实数据。
"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db.database import DatabaseClient, FetchStatus, DataBaseDOINotExists


@pytest.fixture
def db():
    """创建临时数据库的 fixture，测试结束后自动销毁。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_client = DatabaseClient(path)
    db_client.init_db_papers()
    yield db_client
    # 清理
    os.unlink(path)


# ---- 基本操作 ----

def test_init_creates_table(db):
    """验证表创建后可以正常写入。"""
    db.insert_rss_basicinfo("10.0000/test", "Test Title", "http://example.com",
                            "J. Test", "testpub", "2025-01-01")
    assert db.paper_doi_exists("10.0000/test") is True


def test_doi_not_exists(db):
    """验证不存在的 DOI 返回 False。"""
    assert db.paper_doi_exists("10.0000/nonexist") is False


def test_doi_exists_case_insensitive(db):
    """DOI 大小写不敏感：RSS 大写与 CrossRef 小写应命中同一记录。"""
    db.insert_rss_basicinfo("10.1364/OE.605615", "Case Paper", "http://x",
                            "Optics Express", "optica", "2026-08-07")
    assert db.paper_doi_exists("10.1364/OE.605615") is True
    assert db.paper_doi_exists("10.1364/oe.605615") is True
    papers = db.get_all_papers()
    assert papers[0]["doi"] == "10.1364/oe.605615"


def test_insert_lowercases_doi(db):
    """insert_rss_basicinfo / insert_paper_basicinfo 自动把 DOI 转小写。"""
    db.insert_rss_basicinfo("10.1000/B001", "T", "http://a", "J", "pub", "2025")
    db.insert_paper_basicinfo(doi="10.1000/C002", title="U", link="http://b",
                              journal="J", publisher="pub", date="2025",
                              source="crossref")
    dois = {p["doi"] for p in db.get_all_papers()}
    assert dois == {"10.1000/b001", "10.1000/c002"}


def test_is_doi_skipped_case_insensitive(db):
    """skipped_dois 判定大小写不敏感，且写入时规范为小写。"""
    db.insert_skipped_doi("10.1364/OPEX.123456", "NonResearchPageError")
    assert db.is_doi_skipped("10.1364/OPEX.123456") is True
    assert db.is_doi_skipped("10.1364/opex.123456") is True
    # 写入应已小写
    cur = db.conn.execute("SELECT doi FROM skipped_dois")
    assert cur.fetchone()["doi"] == "10.1364/opex.123456"


def test_insert_paper_created_date_case_insensitive(db):
    """insert_paper_created_date 对大小写不敏感地匹配论文。"""
    db.insert_rss_basicinfo("10.1364/OE.605615", "T", "http://x",
                            "J", "pub", "2026")
    db.insert_paper_created_date("10.1364/oe.605615", "2026-08-09")
    papers = db.get_all_papers()
    assert papers[0]["created_date"] == "2026-08-09"


def test_insert_rss_basicinfo(db):
    """验证 RSS 基本写入后数据正确。"""
    db.insert_rss_basicinfo("10.1000/a001", "Paper A", "http://a.com",
                            "J.A", "pubA", "2025-06-01")
    papers = db.get_pendings("cr_metadata_fetched_status")
    assert len(papers) == 1
    assert papers[0]["doi"] == "10.1000/a001"
    assert papers[0]["title"] == "Paper A"
    assert papers[0]["journal"] == "J.A"
    assert papers[0]["page_url"] == "http://a.com"


def test_insert_paper_created_date(db):
    """验证 created_date 更新正确。"""
    db.insert_rss_basicinfo("10.0000/a", "T", "http://x", "J", "pub", "2025")
    db.insert_paper_created_date("10.0000/a", "2025-05-18")
    papers = db.get_all_papers()
    assert papers[0]["created_date"] == "2025-05-18"


# ---- Phase B: CrossRef ----

def test_update_crossref_metadata(db):
    """验证 CrossRef 元数据更新正常。"""
    db.insert_rss_basicinfo("10.0000/b", "Old", "http://b", "J.B", "pubB", "2025")
    authors_json = json.dumps([{"name": "Alice"}, {"name": "Bob"}])
    db.update_crossref_metadata("10.0000/b", "New Title", authors_json, "2025-06-15",
                                "This is the abstract.")
    papers = db.get_all_papers()
    assert papers[0]["title"] == "New Title"
    assert papers[0]["paperdate_crossref"] == "2025-06-15"
    assert papers[0]["abstract"] == "This is the abstract."


def test_update_crossref_nonexistent_doi_raises(db):
    """更新不存在的 DOI 应抛出 DataBaseDOINotExists。"""
    with pytest.raises(DataBaseDOINotExists):
        db.update_crossref_metadata("10.0000/ghost", "T", "[]", "2025", "")


# ---- Phase C: Publisher page ----

def test_update_publisher_page(db):
    """验证出版商页面数据更新。"""
    db.insert_rss_basicinfo("10.0000/c", "T", "http://c", "J", "pub", "2025")
    status_date = "2025-06-01T12:00:00"
    db.update_publisher_page(
        "10.0000/c", "This is abstract", "[{\"name\":\"X\"}]",
        "http://pdf", "2025-06-01",
        FetchStatus.SUCCESS.value, status_date
    )
    papers = db.get_all_papers()
    assert papers[0]["abstract"] == "This is abstract"
    assert papers[0]["publisher_page_fetched_status"] == "success"


# ---- Phase E: LLM 相关性 ----

def test_update_llm_relevance(db):
    """验证 LLM 相关性结果更新（新 A/B/C/D 格式）。"""
    db.insert_rss_basicinfo("10.0000/e", "T", "http://e", "J", "pub", "2025")
    db.update_llm_relevance("10.0000/e", "A", '["test"]', "high", "Very relevant",
                            FetchStatus.SUCCESS.value, "2025")
    papers = db.get_all_papers()
    assert papers[0]["llm_relevance_category"] == "A"
    assert papers[0]["llm_relevance_confidence"] == "high"
    assert papers[0]["llm_relevance_status"] == "success"


def test_update_llm_relevance_error(db):
    """验证 LLM 相关性错误记录。"""
    db.insert_rss_basicinfo("10.0000/e2", "T", "http://e", "J", "pub", "2025")
    db.update_llm_relevance_error("10.0000/e2", "Timeout",
                                  FetchStatus.FAILED.value, "2025")
    papers = db.get_all_papers()
    assert papers[0]["llm_relevance_error"] == "Timeout"
    assert papers[0]["llm_relevance_status"] == "failed"


def _insert_review_candidate(db, doi, category, confidence, screen_category=None):
    """Insert a full-text relevance paper for manual review tests."""
    db.insert_rss_basicinfo(doi, doi, "http://example.com", "J", "pub", "2025")
    db.update_llm_relevance(
        doi, category, "[]", confidence, "model reason",
        FetchStatus.SUCCESS.value, "2025", basis="fulltext",
    )
    if screen_category:
        db.update_relevance_screen(
            doi, screen_category, "[]", "medium", "screen reason",
            FetchStatus.SUCCESS.value, "2025",
        )


def test_relevance_review_queue_prioritizes_unreviewed_medium_b(db):
    """Manual queue should put unreviewed B/medium papers first."""
    _insert_review_candidate(db, "10.0000/review-c", "C", "high", "C")
    _insert_review_candidate(db, "10.0000/review-b", "B", "medium", "B")
    _insert_review_candidate(db, "10.0000/review-a", "A", "medium", "C")

    rows = db.get_relevance_review_queue(status_filter="pending")
    assert [row["doi"] for row in rows] == [
        "10.0000/review-b",
        "10.0000/review-a",
        "10.0000/review-c",
    ]
    assert db.count_relevance_review_queue(status_filter="pending") == 3
    assert db.count_relevance_review_queue(
        status_filter="pending", disagreement_only=True,
    ) == 1


def test_save_relevance_review_preserves_history_and_snapshot(db):
    """Repeated submissions append audit rows without changing LLM output."""
    _insert_review_candidate(db, "10.0000/review-history", "B", "medium", "A")

    first_id = db.save_relevance_review(
        "10.0000/REVIEW-HISTORY", "B", "具体算法可迁移", "alice",
    )
    second_id = db.save_relevance_review(
        "10.0000/review-history", "C", "全文显示主贡献并不相关", "bob",
    )
    assert second_id > first_id

    rows = db.get_relevance_review_queue(status_filter="reviewed")
    assert len(rows) == 1
    assert rows[0]["review_decision"] == "C"
    assert rows[0]["review_reviewer"] == "bob"
    assert rows[0]["llm_relevance_category"] == "B"
    history = db.conn.execute(
        "SELECT COUNT(*) FROM relevance_reviews WHERE doi = ?",
        ("10.0000/review-history",),
    ).fetchone()[0]
    assert history == 2


def test_save_relevance_review_rejects_invalid_decision(db):
    """Only A/B/C/D/uncertain are accepted as human decisions."""
    _insert_review_candidate(db, "10.0000/review-invalid", "D", "high", "D")
    with pytest.raises(ValueError, match="decision"):
        db.save_relevance_review("10.0000/review-invalid", "maybe")


def test_save_relevance_review_stores_uncertain_in_schema_case(db):
    """The lowercase uncertain decision is accepted by the SQLite CHECK."""
    _insert_review_candidate(db, "10.0000/review-uncertain", "C", "low", "C")

    review_id = db.save_relevance_review(
        "10.0000/review-uncertain", "UNCERTAIN", "需要进一步核对", "alice",
    )

    row = db.conn.execute(
        "SELECT id, decision FROM relevance_reviews WHERE id = ?",
        (review_id,),
    ).fetchone()
    assert row["decision"] == "uncertain"


def test_save_relevance_review_requires_fulltext_result(db):
    """Manual review cannot be attached to an abstract-only paper."""
    db.insert_rss_basicinfo(
        "10.0000/review-abstract", "T", "http://x", "J", "pub", "2025",
    )
    db.update_llm_relevance(
        "10.0000/review-abstract", "B", "[]", "medium", "reason",
        FetchStatus.SUCCESS.value, "2025", basis="abstract_clear_reject",
    )

    with pytest.raises(ValueError, match="full-text"):
        db.save_relevance_review("10.0000/review-abstract", "B")


# ---- Phase F: LLM 总结 ----

def test_update_llm_summary(db):
    """验证 LLM 总结结果更新。"""
    db.insert_rss_basicinfo("10.0000/f", "T", "http://f", "J", "pub", "2025")
    summary = json.dumps({"one_sentence": "核心结论", "motivation_and_goal": "目标"}, ensure_ascii=False)
    db.update_llm_summary("10.0000/f", summary, FetchStatus.SUCCESS.value, "2025")
    papers = db.get_all_papers()
    assert papers[0]["llm_summary_status"] == "success"
    assert "核心结论" in papers[0]["llm_summary_result"]


# ---- 查询方法 ----

def test_get_pendings(db):
    """验证 get_pendings 按状态筛选正确。"""
    # 插入 3 条，其中 1 条标记 CrossRef 为 success，另 2 条保持 pending
    for i in range(3):
        db.insert_rss_basicinfo(f"10.0000/p{i}", f"T{i}", f"http://{i}",
                                f"J{i}", "pub", "2025")
    db.update_process_status("10.0000/p0", "cr_metadata_fetched_status",
                              FetchStatus.SUCCESS.value,
                              "cr_metadata_fetched_date", "2025")
    pending = db.get_pendings("cr_metadata_fetched_status")
    assert len(pending) == 2


def test_get_relevant_papers(db):
    """验证 get_relevant_papers 只返回 A/B 类论文。"""
    db.insert_rss_basicinfo("10.0000/r1", "R1", "http://r1", "J", "pub", "2025-01")
    db.insert_rss_basicinfo("10.0000/r2", "R2", "http://r2", "J", "pub", "2025-02")
    db.update_llm_relevance("10.0000/r1", "A", '["LWFA"]', "high", "Yes",
                            FetchStatus.SUCCESS.value, "2025")
    db.update_llm_relevance("10.0000/r2", "D", '[]', "high", "No",
                            FetchStatus.SUCCESS.value, "2025")
    relevant = db.get_relevant_papers()
    assert len(relevant) == 1
    assert relevant[0]["doi"] == "10.0000/r1"


def test_get_pending_summary_papers_excludes_non_ab_and_non_fulltext(db):
    """Phase F's queue contains only eligible full-text A/B papers."""
    for doi, category, basis in (
        ("10.0000/f-pending-a", "A", "fulltext"),
        ("10.0000/f-pending-c", "C", "fulltext"),
        ("10.0000/f-pending-b-abstract", "B", "abstract_clear_reject"),
    ):
        db.insert_rss_basicinfo(doi, doi, "http://x", "J", "pub", "2025")
        db.update_llm_relevance(
            doi, category, "[]", "high", "reason",
            FetchStatus.SUCCESS.value, "2025", basis=basis,
        )

    pending = db.get_pending_summary_papers()

    assert [row["doi"] for row in pending] == ["10.0000/f-pending-a"]


def test_manual_review_overrides_summary_and_report_category(db):
    """Latest manual decisions control both summary and report eligibility."""
    _insert_review_candidate(db, "10.0000/manual-downgrade", "A", "high")
    _insert_review_candidate(db, "10.0000/manual-promote", "C", "high")
    db.save_relevance_review(
        "10.0000/manual-downgrade", "C", "正文不属于核心范围", "alice",
    )
    db.save_relevance_review(
        "10.0000/manual-promote", "A", "正文明确研究激光驱动束流", "alice",
    )

    pending = db.get_pending_summary_papers()
    assert [row["doi"] for row in pending] == ["10.0000/manual-promote"]
    assert pending[0]["effective_relevance_category"] == "A"

    for doi in ("10.0000/manual-downgrade", "10.0000/manual-promote"):
        db.update_llm_summary(
            doi, '{"one_sentence":"summary"}',
            FetchStatus.SUCCESS.value, "2026-08-30",
        )

    reportable = db.get_papers_for_report()
    assert [row["doi"] for row in reportable] == ["10.0000/manual-promote"]
    assert reportable[0]["manual_relevance_decision"] == "A"
    assert reportable[0]["manual_relevance_notes"] == "正文明确研究激光驱动束流"


def test_relevance_review_queue_can_sort_by_summary_date(db):
    """Summary sorting puts newest completed summaries first and nulls last."""
    for doi, summary_date in (
        ("10.0000/summary-old", "2026-08-28 09:00:00"),
        ("10.0000/summary-new", "2026-08-30 09:00:00"),
    ):
        _insert_review_candidate(db, doi, "B", "high")
        db.update_llm_summary(
            doi, '{"one_sentence":"summary"}',
            FetchStatus.SUCCESS.value, summary_date,
        )
    _insert_review_candidate(db, "10.0000/summary-pending", "B", "high")

    rows = db.get_relevance_review_queue(sort_by="summary")
    assert [row["doi"] for row in rows] == [
        "10.0000/summary-new",
        "10.0000/summary-old",
        "10.0000/summary-pending",
    ]


def test_get_papers_for_report(db):
    """验证 get_papers_for_report 只返回已总结、未报告、且当前仍是 A/B 的论文。"""
    db.insert_rss_basicinfo("10.0000/s1", "S1", "http://s1", "J", "pub", "2025")
    db.insert_rss_basicinfo("10.0000/s2", "S2", "http://s2", "J", "pub", "2025")
    # 必须同时设置 relevance=A（否则新过滤会把 summary 状态孤立）
    db.update_llm_relevance("10.0000/s1", "A", '[]', "high", "ok",
                            FetchStatus.SUCCESS.value, "2025", basis="fulltext")
    db.update_llm_relevance("10.0000/s2", "A", '[]', "high", "ok",
                            FetchStatus.SUCCESS.value, "2025", basis="fulltext")
    db.update_llm_summary("10.0000/s1", '{"x":"y"}',
                          FetchStatus.SUCCESS.value, "2025")
    db.update_llm_summary("10.0000/s2", '{"x":"z"}',
                          FetchStatus.SUCCESS.value, "2025")
    # s2 已报告，s1 未报告
    db.mark_papers_reported(["10.0000/s2"], "2025")
    papers = db.get_papers_for_report()
    assert len(papers) == 1
    assert papers[0]["doi"] == "10.0000/s1"


def test_get_papers_for_report_excludes_reclassified_papers(db):
    """回归测试：论文重判为 C/D 后，即使 summary 仍 success，也不应入报。

    背景：update_llm_relevance() 不重置 llm_summary_* 字段。修复前会出现
    「summary 成功 + 当前 C/D」被误入报；修复后应被显式 relevance 过滤拦截。
    """
    db.insert_rss_basicinfo("10.0000/r1", "R1", "http://r1", "J", "pub", "2025")
    db.update_llm_relevance("10.0000/r1", "A", '["LWFA"]', "high", "是",
                            FetchStatus.SUCCESS.value, "2025-01-01", basis="fulltext")
    db.update_llm_summary("10.0000/r1", '{"one_sentence":"x"}',
                          FetchStatus.SUCCESS.value, "2025-01-02")
    # 此时应该入报
    assert len(db.get_papers_for_report()) == 1
    # 重跑相关性：A → D（llm_summary_status 仍为 'success'，不重置）
    db.update_llm_relevance("10.0000/r1", "D", '[]', "high", "已不再相关",
                            FetchStatus.SUCCESS.value, "2025-07-25")
    # 修复后应被过滤掉
    assert db.get_papers_for_report() == []


def test_get_papers_for_report_requires_fulltext_adjudication(db):
    """A/B papers without a full-text E3 basis must never be reportable."""
    db.insert_rss_basicinfo("10.0000/fallback", "Fallback", "http://fallback",
                            "J", "pub", "2025")
    db.update_llm_relevance(
        "10.0000/fallback", "A", '[]', "high", "screen-only",
        FetchStatus.SUCCESS.value, "2025-01-01", basis="abstract_fallback",
    )
    db.update_llm_summary("10.0000/fallback", '{"one_sentence":"x"}',
                          FetchStatus.SUCCESS.value, "2025-01-02")
    assert db.get_papers_for_report() == []


def test_mark_papers_reported(db):
    """验证 mark_papers_reported 批量标记论文。"""
    db.insert_rss_basicinfo("10.0000/r1", "R1", "http://r1", "J", "pub", "2025")
    db.insert_rss_basicinfo("10.0000/r2", "R2", "http://r2", "J", "pub", "2025")
    db.mark_papers_reported(["10.0000/r1", "10.0000/r2"], "2025-06-01")
    all_papers = db.get_all_papers()
    for p in all_papers:
        assert p["report_status"] == "reported"
        assert p["report_date"] == "2025-06-01"


# ---- 通用状态更新 ----

def test_update_process_status(db):
    """验证通用状态更新方法。"""
    db.insert_rss_basicinfo("10.0000/u1", "T", "http://u", "J", "pub", "2025")
    db.update_process_status("10.0000/u1", "publisher_page_fetched_status",
                              FetchStatus.SKIPPED.value,
                              "publisher_page_fetched_date", "2025")
    papers = db.get_all_papers()
    assert papers[0]["publisher_page_fetched_status"] == "skipped"


def test_update_error_message(db):
    """验证错误信息记录。"""
    db.insert_rss_basicinfo("10.0000/u2", "T", "http://u", "J", "pub", "2025")
    db.update_error_message(
        "10.0000/u2", "publisher_page_fetched_status", FetchStatus.FAILED.value,
        "publisher_page_fetched_error", "Connection refused",
        "publisher_page_fetched_date", "2025"
    )
    papers = db.get_all_papers()
    assert papers[0]["publisher_page_fetched_status"] == "failed"
    assert papers[0]["publisher_page_fetched_error"] == "Connection refused"


# ---- get_papers / get_papers_count 测试 ----

def _insert_sort_papers(db):
    """插入三篇排序测试论文，具有不同的 created_date / paperdate_rss / llm_summary_date。"""
    # Paper A: created=2025-03-01, rss=2025-01-01, summary=2025-06-01
    db.insert_rss_basicinfo("10.9999/sort_a", "Sort A", "http://sort_a",
                            "J.A", "pub", "2025-01-01")
    db.insert_paper_created_date("10.9999/sort_a", "2025-03-01")
    db.update_llm_relevance("10.9999/sort_a", "A", '[]', "high", "",
                            FetchStatus.SUCCESS.value, "2025-06-01")
    db.update_llm_summary("10.9999/sort_a", "{}",
                          FetchStatus.SUCCESS.value, "2025-06-01")

    # Paper B: created=2025-02-01, rss=2025-03-01, summary=2025-05-01
    db.insert_rss_basicinfo("10.9999/sort_b", "Sort B", "http://sort_b",
                            "J.B", "pub", "2025-03-01")
    db.insert_paper_created_date("10.9999/sort_b", "2025-02-01")
    db.update_llm_relevance("10.9999/sort_b", "B", '[]', "high", "",
                            FetchStatus.SUCCESS.value, "2025-06-02")
    db.update_llm_summary("10.9999/sort_b", "{}",
                          FetchStatus.SUCCESS.value, "2025-05-01")

    # Paper C: created=2025-01-01, rss=2025-02-01, summary=NULL（不调用 update_llm_summary）
    db.insert_rss_basicinfo("10.9999/sort_c", "Sort C", "http://sort_c",
                            "J.C", "pub", "2025-02-01")
    db.insert_paper_created_date("10.9999/sort_c", "2025-01-01")
    db.update_llm_relevance("10.9999/sort_c", "C", '[]', "low", "",
                            FetchStatus.SUCCESS.value, "2025-06-03")


def test_get_papers_default_sort_created(db):
    """
    验证 get_papers() 默认按 created_date 降序排列。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_sort_papers(db)
    papers = db.get_papers()
    assert len(papers) == 3
    dois = [p["doi"] for p in papers]
    assert dois == ["10.9999/sort_a", "10.9999/sort_b", "10.9999/sort_c"], \
        f"Expected created DESC order, got {dois}"


def test_get_papers_sort_published(db):
    """
    验证 get_papers(sort_by='published') 按 Coalesced 出版日期降序排列。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_sort_papers(db)
    papers = db.get_papers(sort_by="published")
    assert len(papers) == 3
    dois = [p["doi"] for p in papers]
    # B: 2025-03-01, C: 2025-02-01, A: 2025-01-01
    assert dois == ["10.9999/sort_b", "10.9999/sort_c", "10.9999/sort_a"], \
        f"Expected published DESC order, got {dois}"


def test_get_papers_sort_summary(db):
    """
    验证 get_papers(sort_by='summary') 按 llm_summary_date 降序排列，
    NULL 日期排在最后。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_sort_papers(db)
    papers = db.get_papers(sort_by="summary")
    assert len(papers) == 3
    dois = [p["doi"] for p in papers]
    # A: 2025-06-01, B: 2025-05-01, C: NULL -> last
    assert dois == ["10.9999/sort_a", "10.9999/sort_b", "10.9999/sort_c"], \
        f"Expected summary DESC order, got {dois}"


def test_get_papers_offset_pagination(db):
    """
    验证 offset + limit 分页正确性。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    for i in range(6):
        doi = f"10.9999/page_{i}"
        db.insert_rss_basicinfo(doi, f"Page {i}", f"http://{i}",
                                "J", "pub", "2025-01-01")
        db.insert_paper_created_date(doi, f"2025-06-{i+1:02d}")
        db.update_llm_relevance(doi, "A", '[]', "high", "",
                                FetchStatus.SUCCESS.value, "2025-06-01")

    # 默认按 created_date DESC: page_5, page_4, page_3, page_2, page_1, page_0
    # limit=2, offset=2 -> page_3, page_2
    papers = db.get_papers(limit=2, offset=2)
    assert len(papers) == 2
    assert [p["doi"] for p in papers] == ["10.9999/page_3", "10.9999/page_2"]

    # offset=4, limit=2 -> page_1, page_0
    papers = db.get_papers(limit=2, offset=4)
    assert len(papers) == 2
    assert [p["doi"] for p in papers] == ["10.9999/page_1", "10.9999/page_0"]

    # offset 超出总数 -> 空列表
    papers = db.get_papers(limit=2, offset=10)
    assert len(papers) == 0


def _insert_category_papers(db):
    """插入五篇用于分类过滤测试的论文：A/B/C/D 各一 + 1 篇无 relevance 状态。"""
    # A
    db.insert_rss_basicinfo("10.9999/cat_a", "Cat A", "http://a",
                            "J", "pub", "2025-01-01")
    db.insert_paper_created_date("10.9999/cat_a", "2025-01-01")
    db.update_llm_relevance("10.9999/cat_a", "A", '[]', "high", "",
                            FetchStatus.SUCCESS.value, "2025-06-01")
    # B
    db.insert_rss_basicinfo("10.9999/cat_b", "Cat B", "http://b",
                            "J", "pub", "2025-01-02")
    db.insert_paper_created_date("10.9999/cat_b", "2025-01-02")
    db.update_llm_relevance("10.9999/cat_b", "B", '[]', "high", "",
                            FetchStatus.SUCCESS.value, "2025-06-02")
    # C
    db.insert_rss_basicinfo("10.9999/cat_c", "Cat C", "http://c",
                            "J", "pub", "2025-01-03")
    db.insert_paper_created_date("10.9999/cat_c", "2025-01-03")
    db.update_llm_relevance("10.9999/cat_c", "C", '[]', "low", "",
                            FetchStatus.SUCCESS.value, "2025-06-03")
    # D
    db.insert_rss_basicinfo("10.9999/cat_d", "Cat D", "http://d",
                            "J", "pub", "2025-01-04")
    db.insert_paper_created_date("10.9999/cat_d", "2025-01-04")
    db.update_llm_relevance("10.9999/cat_d", "D", '[]', "low", "",
                            FetchStatus.SUCCESS.value, "2025-06-04")
    # No relevance（llm_relevance_status 保持默认 pending）
    db.insert_rss_basicinfo("10.9999/cat_p", "Cat P", "http://p",
                            "J", "pub", "2025-01-05")
    db.insert_paper_created_date("10.9999/cat_p", "2025-01-05")


def test_get_papers_category_filter_ab(db):
    """
    验证 category_filter='ab' 返回 A 和 B 类论文。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_category_papers(db)
    papers = db.get_papers(category_filter="ab")
    dois = {p["doi"] for p in papers}
    assert dois == {"10.9999/cat_a", "10.9999/cat_b"}, \
        f"Expected A and B, got {dois}"


def test_get_papers_category_filter_a(db):
    """
    验证 category_filter='a' 仅返回 A 类论文。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_category_papers(db)
    papers = db.get_papers(category_filter="a")
    dois = {p["doi"] for p in papers}
    assert dois == {"10.9999/cat_a"}, \
        f"Expected only A, got {dois}"


def test_get_papers_category_filter_b(db):
    """
    验证 category_filter='b' 仅返回 B 类论文。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_category_papers(db)
    papers = db.get_papers(category_filter="b")
    dois = {p["doi"] for p in papers}
    assert dois == {"10.9999/cat_b"}, \
        f"Expected only B, got {dois}"


def test_get_papers_category_filter_all(db):
    """
    验证 category_filter='all' 不过滤，返回全部论文。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_category_papers(db)
    papers_all = db.get_papers(category_filter="all")
    papers_none = db.get_papers()  # category_filter=None
    assert len(papers_all) == 5
    assert len(papers_all) == len(papers_none)


def test_get_papers_count_no_filter(db):
    """
    验证 get_papers_count() 返回全部论文总数。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_category_papers(db)
    assert db.get_papers_count() == 5


def test_get_papers_count_with_category_filter(db):
    """
    验证 get_papers_count(category_filter=...) 对各类别正确计数。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_category_papers(db)
    assert db.get_papers_count(category_filter="a") == 1
    assert db.get_papers_count(category_filter="b") == 1
    assert db.get_papers_count(category_filter="ab") == 2
    assert db.get_papers_count(category_filter="all") == 5
    assert db.get_papers_count() == 5


def test_get_papers_count_matches_get_papers_total(db):
    """
    验证 get_papers_count() 与 get_papers(limit=1000) 返回数量一致。

    覆盖无 filter 及各种 category_filter 值。

    Parameters
    ----------
    db : DatabaseClient
        临时数据库 fixture。
    """
    _insert_category_papers(db)
    count = db.get_papers_count()
    papers = db.get_papers(limit=1000)
    assert count == len(papers), \
        f"get_papers_count={count} != len(get_papers)={len(papers)}"

    for cf in ("a", "b", "ab", "all"):
        count_cf = db.get_papers_count(category_filter=cf)
        papers_cf = db.get_papers(limit=1000, category_filter=cf)
        assert count_cf == len(papers_cf), \
            f"category_filter={cf}: count={count_cf} != len={len(papers_cf)}"


def test_get_papers_summary_filter_matches_count(db):
    """Summary filtering must happen before pagination and count calculation."""
    _insert_sort_papers(db)

    papers = db.get_papers(limit=100, has_summary=True)

    assert [paper["doi"] for paper in papers] == [
        "10.9999/sort_a", "10.9999/sort_b",
    ]
    assert db.get_papers_count(has_summary=True) == 2


def test_normalize_metadata_text_repairs_legacy_entities(db):
    """Legacy encoded abstract entities are repaired by the metadata migration."""
    db.insert_rss_basicinfo(
        "10.0000/encoded", "Title&#xD;Part", "https://example.com",
        "Journal", "Publisher", "2026-08-23",
    )
    db.conn.execute(
        "UPDATE papers SET abstract = ? WHERE doi = ?",
        ("first&#xD;second", "10.0000/encoded"),
    )
    db.conn.commit()

    assert db.normalize_metadata_text() == 1
    paper = db.conn.execute(
        "SELECT title, abstract FROM papers WHERE doi = ?",
        ("10.0000/encoded",),
    ).fetchone()
    assert paper["title"] == "Title Part"
    assert paper["abstract"] == "first second"
