from __future__ import annotations

import math
import random

from .elo_ranker import rank_candidates
from .schemas import BotMoveRequest, BotMoveResponse, CandidateMove
from .strategy.plan_engine import get_plan_recommendations
from .stockfish_engine import StockfishEngine


def choose_bot_move(request: BotMoveRequest) -> BotMoveResponse:
    if request.selected_bot_plan_id:
        plan_response = get_plan_recommendations(
            fen=request.fen,
            selected_plan_id=request.selected_bot_plan_id,
            elo=request.elo,
            move_history=(request.strategy_state or {}).get("moveHistoryUci", []),
            skill_level=request.skill_level,
            max_moves=request.max_moves,
            engine_depth=request.engine_depth,
        )
        plan_candidates = candidates_from_plan_response(plan_response)
        if plan_candidates:
            pool = candidate_pool_for_elo(plan_candidates, request.elo)
            selected = weighted_choice(pool, request.elo, request.bot_style)
            return BotMoveResponse(
                move=selected,
                selectionReason="Le bot choisit un coup cohérent avec son plan et adapté à cet Elo.",
                updatedStrategyState=request.strategy_state or {},
                explanationPreview=selected.summary,
            )

    multipv = min(30, request.max_moves * 3)
    lines = StockfishEngine().analyze(request.fen, multipv=multipv, depth=request.engine_depth)
    candidates = rank_candidates(request.fen, lines, request.elo, max_moves=10)
    if not candidates:
        raise RuntimeError("No legal bot move available.")

    pool = candidate_pool_for_elo(candidates, request.elo)
    pool = safety_filter(pool, candidates[0], request.elo, request.bot_style)
    selected = weighted_choice(pool, request.elo, request.bot_style)

    return BotMoveResponse(
        move=selected,
        selectionReason=selection_reason(request.elo, request.bot_style),
        updatedStrategyState=request.strategy_state or {},
        explanationPreview=selected.summary,
    )


def candidates_from_plan_response(plan_response: dict) -> list[CandidateMove]:
    ordered_items = []
    if plan_response.get("primaryMove"):
        ordered_items.append(plan_response["primaryMove"])
    ordered_items.extend(plan_response.get("adaptedAlternatives", []))
    if not ordered_items:
        ordered_items.extend(plan_response.get("mergedRecommendations", []))
    candidates = []
    seen = set()
    for item in ordered_items:
        candidate_data = item.get("candidate") if isinstance(item, dict) else None
        if not candidate_data:
            continue
        move_uci = candidate_data.get("moveUci")
        if move_uci in seen:
            continue
        seen.add(move_uci)
        candidates.append(CandidateMove.model_validate(candidate_data))
    return candidates


def candidate_pool_for_elo(candidates: list[CandidateMove], elo: int) -> list[CandidateMove]:
    if elo <= 1000:
        limit = 10
    elif elo <= 1800:
        limit = 6
    elif elo <= 2600:
        limit = 4
    else:
        limit = 2
    return candidates[: min(limit, len(candidates))]


def safety_filter(pool: list[CandidateMove], best: CandidateMove, elo: int, style: str) -> list[CandidateMove]:
    if style == "aggressive" and elo <= 1400:
        return pool
    threshold = 28 if elo < 1200 else 18
    filtered = [
        candidate
        for candidate in pool
        if best.coach_score - candidate.coach_score <= threshold or candidate.simplicity_score >= 70
    ]
    return filtered or pool[:1]


def weighted_choice(pool: list[CandidateMove], elo: int, style: str) -> CandidateMove:
    temperature = temperature_for_elo(elo)
    style_bonus = {"safe": 1.08, "balanced": 1.0, "aggressive": 0.96}.get(style, 1.0)
    weights = [math.exp((candidate.coach_score * style_bonus) / temperature) for candidate in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def temperature_for_elo(elo: int) -> float:
    if elo <= 1000:
        return 28.0
    if elo <= 1800:
        return 18.0
    if elo <= 2600:
        return 11.0
    return 5.0


def selection_reason(elo: int, style: str) -> str:
    if elo <= 1000:
        return "Le bot a choisi un coup naturel pour ce niveau, avec un peu de variété."
    if style in {"safe", "solid", "educational"}:
        return "Le bot a privilégié un coup sûr et facile à expliquer."
    if style == "aggressive":
        return "Le bot a choisi un coup actif tout en restant dans les recommandations."
    return "Le bot a choisi un coup cohérent avec le score coach et le niveau Elo."
