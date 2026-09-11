from config import settings


def test_copilot_is_optional_without_an_openai_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert settings.is_catalogguard_agent_configured() is False


def test_copilot_model_uses_one_environment_config_point(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_AGENT_MODEL", "gpt-5.6-sol")

    assert settings.get_catalogguard_agent_model() == "gpt-5.6-sol"


def test_copilot_provider_defaults_to_openai_for_backward_compatibility(monkeypatch):
    monkeypatch.delenv("CATALOGGUARD_AGENT_PROVIDER", raising=False)

    assert settings.get_catalogguard_agent_provider() == "openai"


def test_ollama_provider_does_not_require_an_openai_api_key(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_AGENT_PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CATALOGGUARD_AGENT_MODEL", raising=False)

    assert settings.is_catalogguard_agent_configured() is True
    assert settings.get_catalogguard_agent_model() == "qwen3.5:9b"


def test_invalid_copilot_provider_is_not_configured(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_AGENT_PROVIDER", "unsupported")

    assert settings.is_catalogguard_agent_provider_valid() is False
    assert settings.is_catalogguard_agent_configured() is False


def test_ollama_base_url_uses_the_local_compatible_endpoint_by_default(monkeypatch):
    monkeypatch.delenv("CATALOGGUARD_OLLAMA_BASE_URL", raising=False)

    assert settings.get_catalogguard_ollama_base_url() == "http://localhost:11434/v1/"
