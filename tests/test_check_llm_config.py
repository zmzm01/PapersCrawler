"""Tests for the non-billing LLM provider diagnostic."""

from tools import check_llm_config


class _Response:
    """Minimal successful model-catalogue response."""

    def raise_for_status(self):
        """Represent an HTTP success."""

    def json(self):
        """Return a representative model catalogue."""
        return {"data": [{"id": "model/a"}, {"id": "model/b"}]}


class _Session:
    """Capture diagnostic request metadata."""

    def __init__(self):
        self.headers = None

    def get(self, _url, headers, timeout):
        """Return the fixed catalogue response."""
        assert timeout == 30
        self.headers = headers
        return _Response()


def test_fetch_model_ids_uses_active_provider_credentials(monkeypatch):
    """Catalogue checks authenticate without sending a completion request."""
    monkeypatch.setattr(
        check_llm_config.CFG, "LLM_MODEL_LIST_URL", "https://example/models",
    )
    monkeypatch.setattr(check_llm_config.CFG, "LLM_API_KEY", "secret")
    session = _Session()
    assert check_llm_config.fetch_model_ids(session) == {"model/a", "model/b"}
    assert session.headers == {"Authorization": "Bearer secret"}


def test_similar_model_ids_finds_same_family():
    """Missing provider aliases receive bounded same-family suggestions."""
    available = {"z-ai/glm-5", "other/model", "z-ai/glm-4.5-air"}
    assert check_llm_config.similar_model_ids(
        "zai-org/GLM-5.2", available,
    ) == ["z-ai/glm-4.5-air", "z-ai/glm-5"]
