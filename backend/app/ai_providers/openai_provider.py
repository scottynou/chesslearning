from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from .base import BEGINNER_SYSTEM_PROMPT, EXPLAIN_CANDIDATE_SCHEMA, AiProvider, build_user_prompt


class OpenAiProvider(AiProvider):
    def explain_candidate(self, context: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        client = OpenAI(api_key=api_key, timeout=timeout_seconds)
        model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": BEGINNER_SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(context)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "beginner_chess_explanation",
                    "schema": EXPLAIN_CANDIDATE_SCHEMA,
                    "strict": True,
                }
            },
        )
        return json.loads(response.output_text)
