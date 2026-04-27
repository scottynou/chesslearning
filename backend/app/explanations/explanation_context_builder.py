from __future__ import annotations

from typing import Any

from ..beginner_notation import beginner_notation_for_uci
from ..evaluation_label import evaluation_label
from ..pv_translator import translate_pv


def build_plan_explanation_context(
    *,
    fen: str,
    user_level: int,
    selected_plan: dict[str, Any] | None,
    plan_state: dict[str, Any] | None,
    selected_recommendation: dict[str, Any],
    alternatives: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate = selected_recommendation.get("candidate") or {}
    move_uci = selected_recommendation["moveUci"]
    notation = beginner_notation_for_uci(fen, move_uci, selected_recommendation.get("moveSan"))
    return {
        "userLevel": user_level,
        "beginnerMode": True,
        "selectedPlan": {
            "name": selected_plan.get("nameFr") if selected_plan else "Plan général",
            "currentGoal": (plan_state or {}).get("nextObjectives", ["Comprendre la position"])[0],
        },
        "positionFacts": {
            "sideToMove": (plan_state or {}).get("side"),
            "phase": (plan_state or {}).get("phase"),
            "kingSafety": "",
            "center": "",
            "undevelopedPieces": [],
            "hangingPieces": [],
            "weakSquares": [],
            "openFiles": [],
        },
        "selectedMove": {
            "beginnerLabel": notation.beginner_label,
            "san": notation.san,
            "uci": move_uci,
            "source": selected_recommendation.get("source"),
            "engineEvalLabel": selected_recommendation.get("evalLabel") or evaluation_label(candidate.get("evalCp"), candidate.get("mateIn")),
            "planConnection": selected_recommendation.get("planConnection"),
        },
        "engineEvidence": {
            "stockfishRank": selected_recommendation.get("engineRank"),
            "evalBefore": selected_recommendation.get("evalLabel"),
            "evalAfter": selected_recommendation.get("evalLabel"),
            "pvTranslated": [item["simpleExplanation"] for item in translate_pv(fen, candidate.get("pv", []), limit=4)],
        },
        "alternatives": [
            {
                "beginnerLabel": item.get("beginnerLabel"),
                "whyLessPreferred": item.get("planConnection") or item.get("purpose"),
            }
            for item in alternatives[:3]
        ],
    }
