from __future__ import annotations

import os


def configured_provider_name() -> str:
    provider = os.getenv("AI_PROVIDER", "auto").lower().strip()
    if provider != "auto":
        return provider
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("OLLAMA_BASE_URL"):
        return "ollama"
    return "heuristic"
