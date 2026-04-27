from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .base import BEGINNER_SYSTEM_PROMPT, EXPLAIN_CANDIDATE_SCHEMA, AiProvider, build_user_prompt


class OllamaProvider(AiProvider):
    def explain_candidate(self, context: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", "qwen3:8b")
        response = httpx.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "system": BEGINNER_SYSTEM_PROMPT,
                "prompt": build_user_prompt(context),
                "stream": False,
                "format": EXPLAIN_CANDIDATE_SCHEMA,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        content = response.json().get("response", "{}")
        return json.loads(content)
