from __future__ import annotations

import os
from typing import Any

from .ai_providers.gemini_provider import GeminiProvider
from .ai_providers.heuristic_provider import HeuristicProvider
from .ai_providers.ollama_provider import OllamaProvider
from .ai_providers.openai_provider import OpenAiProvider
from .ai_providers.selection import configured_provider_name
from .schemas import LivePlanInsightRequest, LivePlanInsightResponse
from .strategy.opening_coach import get_plan


LIVE_PLAN_PROVIDERS = {
    "heuristic": HeuristicProvider,
    "openai": OpenAiProvider,
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
}


def live_plan_insight(request: LivePlanInsightRequest) -> LivePlanInsightResponse:
    context = {
        "fen": request.fen,
        "moveHistoryUci": request.move_history_uci,
        "phase": request.phase,
        "phaseLabel": _phase_label(request.phase),
        "openingState": request.opening_state,
        "selectedPlan": get_plan(request.selected_plan_id),
        "strategicPlan": request.strategic_plan,
        "primaryMove": request.primary_move,
        "expectedOpponentMove": request.expected_opponent_move,
        "planEvent": request.plan_event,
    }
    provider_name = configured_provider_name()
    provider_cls = LIVE_PLAN_PROVIDERS.get(provider_name, HeuristicProvider)
    timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "12"))

    try:
        data = provider_cls().live_plan(context, timeout_seconds=timeout)
        payload = _coerce_payload(data, request.plan_event)
        return LivePlanInsightResponse(
            **payload,
            analysisProvider=provider_name if provider_name in LIVE_PLAN_PROVIDERS else "heuristic",
            analysisKind="heuristic" if provider_name == "heuristic" else "ai",
        )
    except Exception:
        fallback = HeuristicProvider().live_plan(context, timeout_seconds=0)
        payload = _coerce_payload(fallback, request.plan_event)
        return LivePlanInsightResponse(**payload, analysisProvider="heuristic", analysisKind="heuristic")


def _coerce_payload(data: dict[str, Any], fallback_event: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "headline": str(data.get("headline") or "Plan actuel").strip(),
        "currentPlan": str(data.get("currentPlan") or "Jouer simple, garder le roi en securite et ameliorer les pieces.").strip(),
        "whyChanged": str(data.get("whyChanged") or "La position demande surtout de garder un plan clair.").strip(),
        "nextGoal": str(data.get("nextGoal") or "Trouver le coup le plus simple qui aide le plan.").strip(),
        "event": data.get("event") or fallback_event,
    }


def _phase_label(phase: str) -> str:
    return {"opening": "Ouverture", "transition": "Milieu de partie", "middlegame": "Milieu de partie", "endgame": "Finale"}.get(phase, phase)
