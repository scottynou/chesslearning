from app.ai_providers.selection import configured_provider_name


def test_auto_provider_uses_heuristic_without_ai_keys(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    assert configured_provider_name() == "heuristic"


def test_auto_provider_prefers_gemini_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")

    assert configured_provider_name() == "gemini"
