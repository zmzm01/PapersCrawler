"""Coverage for retry, circuit-breaker and protocol edge cases."""

import json
from types import SimpleNamespace

import pytest
import requests

import common
from processors.report_snapshot import build_report_papers, make_report_identifier


def _response(status=200, data=None, text=""):
    response = requests.Response()
    response.status_code = status
    response._content = text.encode("utf-8")
    response.headers = {}
    response.json = lambda: data
    return response


def test_circuit_breaker_resets_and_closes():
    """Transient failures open the circuit and success resets the counter."""
    breaker = common.LLMCircuitBreaker(2)
    assert breaker.allow_request()
    breaker.record_transient_failure()
    assert not breaker.is_open
    breaker.record_success()
    breaker.record_transient_failure()
    breaker.record_transient_failure()
    assert breaker.is_open
    assert not breaker.allow_request()
    assert common.LLMCircuitBreaker(0).failure_threshold == 1


def test_retry_delay_honours_header_and_fallback(monkeypatch):
    """Numeric, invalid and absent Retry-After values are all bounded."""
    monkeypatch.setattr(common.random, "uniform", lambda low, high: 1.0)
    assert (
        common._retry_delay(SimpleNamespace(headers={"Retry-After": "3"}), 0, 10) == 3
    )
    assert (
        common._retry_delay(SimpleNamespace(headers={"Retry-After": "bad"}), 2, 10) == 4
    )
    assert common._retry_delay(None, 5, 2) == 2


def test_call_llm_api_success_and_protocol_plain_text(monkeypatch):
    """Successful calls normalize a response and can preserve plain text."""

    class Session:
        def __init__(self, response):
            self.response = response
            self.requests = []

        def post(self, url, **kwargs):
            self.requests.append((url, kwargs))
            return self.response

    session = Session(
        _response(data={"choices": [{"message": {"content": '{"ok": true}'}}]})
    )
    assert (
        common.call_llm_api_with_retry(
            {"api_url": "https://llm", "retry_max_attempts": 1},
            {"Authorization": "Bearer x"},
            {"messages": []},
            session=session,
        )
        == '{"ok": true}'
    )
    assert session.requests[0][1]["json"] == {"messages": []}

    response_session = Session(
        _response(
            data={"output": [{"content": [{"type": "output_text", "text": "plain"}]}]}
        )
    )
    assert (
        common.call_llm_api_with_retry(
            {
                "api_url": "https://llm",
                "protocol": "openai_responses",
                "retry_max_attempts": 1,
            },
            {},
            {"model": "m", "messages": [{"role": "user", "content": "x"}]},
            session=response_session,
            expect_json=False,
        )
        == "plain"
    )


def test_call_llm_api_errors_and_circuit(monkeypatch):
    """HTTP, malformed response and open-circuit failures are classified."""
    monkeypatch.setattr(common.time, "sleep", lambda _: None)

    class ErrorSession:
        def __init__(self, error):
            self.error = error

        def post(self, *args, **kwargs):
            if isinstance(self.error, BaseException):
                raise self.error
            return self.error

    response = _response(401, data={"error": "bad key"}, text="bad key")
    http_error = requests.HTTPError("unauthorized", response=response)
    with pytest.raises(common.LLMAPICallError, match="401"):
        common.call_llm_api_with_retry(
            {"api_url": "https://llm", "retry_max_attempts": 1},
            {},
            {},
            session=ErrorSession(http_error),
        )

    breaker = common.LLMCircuitBreaker(1)
    with pytest.raises(common.LLMServiceUnavailableError):
        common.call_llm_api_with_retry(
            {"api_url": "https://llm", "retry_max_attempts": 1},
            {},
            {},
            session=ErrorSession(requests.ConnectionError("offline")),
            circuit_breaker=breaker,
        )
    assert breaker.is_open
    with pytest.raises(common.LLMServiceUnavailableError, match="open"):
        common.call_llm_api_with_retry(
            {"api_url": "https://llm"}, {}, {}, circuit_breaker=breaker
        )

    missing = ErrorSession(_response(data={"message": "temporarily unavailable"}))
    with pytest.raises(common.LLMServiceUnavailableError):
        common.call_llm_api_with_retry(
            {"api_url": "https://llm", "retry_max_attempts": 1},
            {},
            {},
            session=missing,
        )

    malformed = ErrorSession(
        _response(data={"choices": [{"message": {"content": '{"x": "unterminated}'}}]})
    )
    with pytest.raises(common.LLMResponseParseError):
        common.call_llm_api_with_retry(
            {"api_url": "https://llm", "retry_max_attempts": 1},
            {},
            {},
            session=malformed,
        )


def test_protocol_helpers_cover_anthropic_and_invalid_response():
    """Anthropic translation and invalid protocol content have explicit errors."""
    payload = {
        "model": "m",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u"},
        ],
        "thinking": {"type": "enabled"},
    }
    translated = common._build_protocol_payload(
        {"protocol": "anthropic_messages", "max_tokens": 12}, payload
    )
    assert translated["system"] == "sys"
    assert translated["thinking"] == {"type": "adaptive"}
    headers = common._build_protocol_headers(
        {"protocol": "anthropic_messages", "api_key": "k"}, {"Authorization": "old"}
    )
    assert headers["x-api-key"] == "k"
    assert "Authorization" not in headers
    with pytest.raises(ValueError):
        common._build_protocol_payload({"protocol": "bad"}, {})
    with pytest.raises(ValueError):
        common._extract_protocol_content("bad", {})
    with pytest.raises(KeyError):
        common._extract_protocol_content(
            "anthropic_messages", {"content": [{"type": "image"}]}
        )


def test_report_snapshot_normalizes_authors_and_bad_json():
    """Snapshot conversion handles fallback dates and malformed columns."""
    row = {
        "title": None,
        "authors_json": json.dumps([{"name": "Alice"}, {"family": "ignored"}]),
        "paperdate_crossref": "",
        "paperdate_page": "2026",
        "paperdate_rss": "2025",
        "doi": "10/x",
        "journal": None,
        "publisher": None,
        "llm_relevance_subfields": "not-json",
        "llm_relevance_category": None,
        "llm_relevance_reason": None,
        "llm_relevance_basis": None,
        "page_url": None,
        "pdf_url": None,
        "abstract": "raw",
        "llm_summary_result": "not-json",
        "llm_summary_status": "failed",
    }
    paper = build_report_papers([row])[0]
    assert paper["authors"] == ["Alice"]
    assert paper["date"] == "2026"
    assert paper["has_full_summary"] is False
    assert make_report_identifier(" Report 2026/08/24 ") == "papers-report-2026-08-24"
    assert make_report_identifier("...") == "papers-report"
