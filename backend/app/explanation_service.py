from __future__ import annotations

import os
from typing import Any

import chess

from .ai_providers.gemini_provider import GeminiProvider
from .ai_providers.heuristic_provider import HeuristicProvider
from .ai_providers.ollama_provider import OllamaProvider
from .ai_providers.openai_provider import OpenAiProvider
from .ai_providers.selection import configured_provider_name
from .beginner_notation import beginner_notation_for_uci
from .evaluation_label import evaluation_label
from .explanation_quality import ExplanationQualityError, assert_beginner_explanation_quality
from .opening_coach import position_context
from .pv_translator import translate_pv
from .schemas import (
    ExplainCandidateRequest,
    ExplainCandidateResponse,
    ExplainRequest,
    ExplainResponse,
)


PROVIDERS = {
    "heuristic": HeuristicProvider,
    "openai": OpenAiProvider,
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
}


def explain_candidate(request: ExplainCandidateRequest) -> ExplainCandidateResponse:
    context = build_explanation_context(request)
    provider_name = configured_provider_name()
    provider_cls = PROVIDERS.get(provider_name, HeuristicProvider)
    timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "18"))

    for attempt in range(2):
        try:
            data = provider_cls().explain_candidate(context, timeout_seconds=timeout)
            assert_beginner_explanation_quality(data, context["selectedMove"]["pieceName"])
            return ExplainCandidateResponse.model_validate(data)
        except Exception:
            if attempt == 0 and provider_name != "heuristic":
                continue
            break

    fallback = HeuristicProvider().explain_candidate(context, timeout_seconds=0)
    try:
        assert_beginner_explanation_quality(fallback, context["selectedMove"]["pieceName"])
    except ExplanationQualityError:
        pass
    return ExplainCandidateResponse.model_validate(fallback)


def build_explanation_context(request: ExplainCandidateRequest) -> dict[str, Any]:
    selected = request.selected_move
    move_notation = beginner_notation_for_uci(request.fen, selected.move_uci, selected.move_san)
    board = chess.Board(request.fen)

    alternatives = []
    for candidate in request.all_candidates[:4]:
        notation = beginner_notation_for_uci(request.fen, candidate.move_uci, candidate.move_san)
        alternatives.append(
            {
                "beginnerLabel": notation.beginner_label,
                "evalLabel": evaluation_label(candidate.eval_cp, candidate.mate_in),
            }
        )

    selected_move = {
        **move_notation.as_dict(),
        "evalLabel": evaluation_label(selected.eval_cp, selected.mate_in),
        "risk": _fr_risk(selected.risk),
        "difficulty": _fr_difficulty(selected.difficulty),
    }

    return {
        "elo": request.elo,
        "sideToMove": "white" if board.turn == chess.WHITE else "black",
        "selectedMove": selected_move,
        "selectedMoveRaw": selected.model_dump(by_alias=True),
        "positionContext": position_context(board),
        "translatedPv": translate_pv(request.fen, selected.pv, limit=5),
        "topAlternatives": alternatives,
        "beginnerMode": request.beginner_mode,
    }


def explain_move(request: ExplainRequest) -> ExplainResponse:
    modern = explain_candidate(
        ExplainCandidateRequest(
            fen=request.fen,
            elo=request.elo,
            selectedMove=request.selected_move,
            allCandidates=request.all_candidates,
            moveHistoryPgn=request.move_history_pgn,
            beginnerMode=True,
        )
    )
    return ExplainResponse(
        moveSan=modern.technical.san,
        title=modern.title,
        explanation={
            "mainIdea": modern.sections.main_idea,
            "whyForThisElo": modern.sections.why_now,
            "expectedOpponentReaction": modern.sections.what_it_provokes,
            "planA": " ".join(modern.sections.next_plan[:2]),
            "planB": modern.sections.better_than,
            "whatToWatch": modern.sections.danger,
            "commonMistake": modern.sections.common_mistake,
            "comparison": modern.sections.better_than,
        },
    )


def _fr_risk(risk: str) -> str:
    return {"low": "bas", "medium": "moyen", "high": "haut"}.get(risk, risk)


def _fr_difficulty(difficulty: str) -> str:
    return {"easy": "facile", "medium": "moyen", "hard": "difficile"}.get(difficulty, difficulty)
