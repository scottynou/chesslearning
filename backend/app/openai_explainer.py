from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from .heuristic_explainer import explain_heuristically
from .schemas import ExplainRequest, ExplainResponse


SYSTEM_PROMPT = (
    "Tu es un coach d'échecs pédagogique. Tu expliques les coups à un joueur du niveau Elo donné. "
    "Tu ne choisis pas les coups toi-même : les coups viennent d'un moteur. Tu dois expliquer le but, "
    "le plan, les réactions adverses probables, les pièges, et pourquoi le coup est adapté ou non au niveau. "
    "Tu dois parler simplement, en français, sans jargon inutile. Si les données moteur ne suffisent pas, "
    "dis-le prudemment."
)


EXPLANATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["moveSan", "title", "explanation"],
    "properties": {
        "moveSan": {"type": "string"},
        "title": {"type": "string"},
        "explanation": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "mainIdea",
                "whyForThisElo",
                "expectedOpponentReaction",
                "planA",
                "planB",
                "whatToWatch",
                "commonMistake",
                "comparison",
            ],
            "properties": {
                "mainIdea": {"type": "string"},
                "whyForThisElo": {"type": "string"},
                "expectedOpponentReaction": {"type": "string"},
                "planA": {"type": "string"},
                "planB": {"type": "string"},
                "whatToWatch": {"type": "string"},
                "commonMistake": {"type": "string"},
                "comparison": {"type": "string"},
            },
        },
    },
}


def explain_with_openai(request: ExplainRequest) -> ExplainResponse:
    if not os.getenv("OPENAI_API_KEY"):
        return explain_heuristically(request)

    client = OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    payload = request.model_dump(by_alias=True)
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Explique le coup sélectionné en JSON strict. "
                    "N'invente aucune variante absente de pv ou des candidats.\n\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "move_explanation",
                "schema": EXPLANATION_SCHEMA,
                "strict": True,
            }
        },
    )

    data = json.loads(response.output_text)
    return ExplainResponse.model_validate(data)
