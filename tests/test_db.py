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
    """验证 LLM 相关性结果更新。"""
    db.insert_rss_basicinfo("10.0000/e", "T", "http://e", "J", "pub", "2025")
    db.update_llm_relevance("10.0000/e", 1, "high", "Very relevant",
                            FetchStatus.SUCCESS.value, "2025")
    papers = db.get_all_papers()
    assert papers[0]["llm_relevance_result"] == 1
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
    """验证 get_relevant_papers 只返回判定为相关的论文。"""
    db.insert_rss_basicinfo("10.0000/r1", "R1", "http://r1", "J", "pub", "2025-01")
    db.insert_rss_basicinfo("10.0000/r2", "R2", "http://r2", "J", "pub", "2025-02")
    db.update_llm_relevance("10.0000/r1", 1, "high", "Yes",
                            FetchStatus.SUCCESS.value, "2025")
    db.update_llm_relevance("10.0000/r2", 0, "high", "No",
                            FetchStatus.SUCCESS.value, "2025")
    relevant = db.get_relevant_papers()
    assert len(relevant) == 1
    assert relevant[0]["doi"] == "10.0000/r1"


def test_get_papers_for_report(db):
    """验证 get_papers_for_report 只返回已总结且未报告的论文。"""
    db.insert_rss_basicinfo("10.0000/s1", "S1", "http://s1", "J", "pub", "2025")
    db.insert_rss_basicinfo("10.0000/s2", "S2", "http://s2", "J", "pub", "2025")
    db.update_llm_summary("10.0000/s1", '{"x":"y"}',
                          FetchStatus.SUCCESS.value, "2025")
    db.update_llm_summary("10.0000/s2", '{"x":"z"}',
                          FetchStatus.SUCCESS.value, "2025")
    # s2 已报告，s1 未报告
    db.mark_papers_reported(["10.0000/s2"], "2025")
    papers = db.get_papers_for_report()
    assert len(papers) == 1
    assert papers[0]["doi"] == "10.0000/s1"


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
