"""Coverage for configuration fallbacks and runtime reload helpers."""

import base64
import copy
import json

import config
import pytest


def _provider_settings(active_provider="openrouter"):
    """Build a complete two-provider LLM fixture."""
    roles = {
        role_name: {"model": f"openrouter/{role_name}"}
        for role_name in config.LLM_ROLE_CONFIG_TARGETS
    }
    command_roles = {
        role_name: {"model": f"command/{role_name}"}
        for role_name in config.LLM_ROLE_CONFIG_TARGETS
    }
    return {
        "llm": {
            "active_provider": active_provider,
            "providers": {
                "openrouter": {
                    "base_url": "https://openrouter.example/v1",
                    "model_list_url": "https://openrouter.example/v1/models",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "protocol": "openai_chat",
                    "roles": roles,
                },
                "command_code": {
                    "base_url": "https://command.example/v1",
                    "api_key_env": "LLM_API_KEY",
                    "protocol": "openai_chat",
                    "roles": command_roles,
                },
            },
        },
    }


def test_named_llm_provider_switches_all_roles(monkeypatch):
    """The active provider supplies endpoints, credentials and every model."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-secret")
    original_configs = {
        target_name: copy.deepcopy(getattr(config.CFG, target_name))
        for target_name in config.LLM_ROLE_CONFIG_TARGETS.values()
    }
    original_scalars = {
        name: getattr(config.CFG, name)
        for name in (
            "LLM_ACTIVE_PROVIDER", "LLM_BASE_URL", "LLM_MODEL_LIST_URL",
            "LLM_API_KEY",
        )
    }
    try:
        config._apply_settings(_provider_settings())
        assert config.CFG.LLM_ACTIVE_PROVIDER == "openrouter"
        assert config.CFG.LLM_API_KEY == "openrouter-secret"
        assert config.CFG.LLM_MODEL_LIST_URL.endswith("/models")
        for role_name, target_name in config.LLM_ROLE_CONFIG_TARGETS.items():
            role_config = getattr(config.CFG, target_name)
            assert role_config["model"] == f"openrouter/{role_name}"
            assert role_config["api_url"].endswith("/chat/completions")
            assert role_config["api_key"] == "openrouter-secret"
        monkeypatch.setenv("LLM_API_KEY", "command-secret")
        config._apply_settings(_provider_settings("command_code"))
        assert config.CFG.LLM_ACTIVE_PROVIDER == "command_code"
        assert config.CFG.LLM_API_KEY == "command-secret"
        for role_name, target_name in config.LLM_ROLE_CONFIG_TARGETS.items():
            role_config = getattr(config.CFG, target_name)
            assert role_config["model"] == f"command/{role_name}"
            assert role_config["api_key"] == "command-secret"
    finally:
        for target_name, original_config in original_configs.items():
            runtime_config = getattr(config.CFG, target_name)
            runtime_config.clear()
            runtime_config.update(original_config)
        for name, value in original_scalars.items():
            setattr(config.CFG, name, value)


def test_named_llm_provider_validation(monkeypatch):
    """Invalid provider selections and missing credentials fail clearly."""
    settings = _provider_settings("missing")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        config._resolve_llm_provider(settings["llm"])
    settings = _provider_settings()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        config._resolve_llm_provider(settings["llm"])


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
