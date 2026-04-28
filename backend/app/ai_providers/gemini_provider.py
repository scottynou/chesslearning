from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .base import (
    BEGINNER_SYSTEM_PROMPT,
    EXPLAIN_CANDIDATE_SCHEMA,
    LIVE_PLAN_SCHEMA,
    LIVE_PLAN_SYSTEM_PROMPT,
    REVIEW_MOVE_SCHEMA,
    REVIEW_SYSTEM_PROMPT,
    AiProvider,
    build_live_plan_prompt,
    build_review_prompt,
    build_user_prompt,
)


class GeminiProvider(AiProvider):
    def explain_candidate(self, context: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        response = httpx.post(
            url,
            headers={"x-goog-api-key": api_key},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": BEGINNER_SYSTEM_PROMPT + "\n\n" + build_user_prompt(context)}],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": EXPLAIN_CANDIDATE_SCHEMA,
                },
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)

    def live_plan(self, context: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        response = httpx.post(
            url,
            headers={"x-goog-api-key": api_key},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": LIVE_PLAN_SYSTEM_PROMPT + "\n\n" + build_live_plan_prompt(context)}],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": LIVE_PLAN_SCHEMA,
                },
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)

    def review_move(self, context: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        response = httpx.post(
            url,
            headers={"x-goog-api-key": api_key},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": REVIEW_SYSTEM_PROMPT + "\n\n" + build_review_prompt(context)}],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": REVIEW_MOVE_SCHEMA,
                },
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
