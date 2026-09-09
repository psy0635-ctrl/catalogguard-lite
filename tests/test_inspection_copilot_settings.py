from config import settings


def test_copilot_is_optional_without_an_openai_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert settings.is_catalogguard_agent_configured() is False


def test_copilot_model_uses_one_environment_config_point(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_AGENT_MODEL", "gpt-5.6-sol")

    assert settings.get_catalogguard_agent_model() == "gpt-5.6-sol"
