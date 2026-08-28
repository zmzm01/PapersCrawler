"""Coverage for configuration fallbacks and runtime reload helpers."""

import base64
import json

import config


def test_yaml_loaders_and_scope_rendering(tmp_path, monkeypatch):
    """Missing, malformed and valid YAML files use documented fallbacks."""
    config_dir = tmp_path / "configs"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    assert config.load_publishers() == []
    assert config.load_keywords()["scope_definition"] == {}
    (config_dir / "publishers.yaml").write_text("bad: [", encoding="utf-8")
    (config_dir / "keywords.yaml").write_text("bad: [", encoding="utf-8")
    assert config.load_publishers() == []
    assert config.load_keywords()["scope_definition"] == {}
    (config_dir / "publishers.yaml").write_text(
        "publishers:\n  - id: j\n", encoding="utf-8"
    )
    (config_dir / "keywords.yaml").write_text(
        "scope_definition: null\n", encoding="utf-8"
    )
    assert config.load_publishers()[0]["id"] == "j"
    assert config.load_keywords()["scope_definition"] is None
    (config_dir / "keywords.yaml").write_text(
        "scope_definition:\n  laser:\n    display_name: Laser\n    topics: [plasma]\n",
        encoding="utf-8",
    )
    assert config.load_keywords()["scope_definition"]["laser"]["topics"] == ["plasma"]
    rendered = config.build_scope_block(
        {
            "laser": {
                "display_name": "Laser",
                "topics": ["plasma"],
                "description": "desc",
            }
        },
        context_gates=[
            {
                "term": "beam",
                "description": "desc",
                "relevant_contexts": ["r"],
                "irrelevant_contexts": ["i"],
            }
        ],
        irrelevant_fields={"description": "deny", "topics": ["biology"]},
        core_anchors=["laser"],
        keyword_catalog=[
            {"id": "k", "terms": ["plasma"], "subdomains": ["laser"]},
            "invalid",
        ],
    )
    assert "Core anchors" in rendered
    assert "Step 1" in rendered
    assert "Step 2" in rendered
    assert "Sub-Domain: laser" in rendered


def test_email_config_recipients_and_token_warning(tmp_path, monkeypatch, caplog):
    """SMTP parsing, recipient fallback and JWT expiry warnings are covered."""
    for name in (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_ADDR",
        "SMTP_TO_ADDRS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert config.load_email_config() == {}
    monkeypatch.setenv("SMTP_HOST", "smtp")
    monkeypatch.setenv("SMTP_PORT", "bad")
    monkeypatch.setenv("SMTP_USERNAME", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    monkeypatch.setenv("SMTP_FROM_ADDR", "f")
    assert config.load_email_config() == {}
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USE_TLS", "no")
    monkeypatch.setenv("SMTP_TO_ADDRS", "a@example.com, b@example.com")
    assert config.load_email_config()["use_tls"] is False
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert config.load_email_recipients() == ["a@example.com", "b@example.com"]
    (tmp_path / "email.yaml").write_text(
        "recipients:\n  - email: enabled@example.com\n    enabled: true\n  - email: off@example.com\n    enabled: false\n",
        encoding="utf-8",
    )
    assert config.load_email_recipients() == ["enabled@example.com"]
    (tmp_path / "email.yaml").write_text("recipients: [", encoding="utf-8")
    assert config.load_email_recipients() == ["a@example.com", "b@example.com"]

    monkeypatch.setattr(config.CFG, "MINERU_TOKEN", "")
    config._check_mineru_token()
    monkeypatch.setattr(config.CFG, "MINERU_TOKEN", "invalid")
    config._check_mineru_token()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": 1}).encode()).decode().rstrip("=")
    )
    monkeypatch.setattr(config.CFG, "MINERU_TOKEN", f"a.{payload}.c")
    config._check_mineru_token()
    assert "过期" in caplog.text
