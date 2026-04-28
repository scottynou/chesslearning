from __future__ import annotations

import math
import random
from typing import Any

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


def candidates_from_plan_response(plan_response: dict[str, Any]) -> list[CandidateMove]:
    ordered_items: list[dict[str, Any]] = []
    if plan_response.get("primaryMove"):
        ordered_items.append(plan_response["primaryMove"])
    ordered_items.extend(plan_response.get("adaptedAlternatives", []))
    if not ordered_items:
        ordered_items.extend(plan_response.get("mergedRecommendations", []))
    candidates = []
    seen = set()
    for item in ordered_items:
        candidate = candidate_from_plan_item(item, rank=len(candidates) + 1)
        if candidate is None:
            continue
        move_uci = candidate.move_uci
        if move_uci in seen:
            continue
        seen.add(move_uci)
        candidates.append(candidate)
    return candidates


def candidate_from_plan_item(item: dict[str, Any], rank: int) -> CandidateMove | None:
    candidate_data = item.get("candidate")
    if candidate_data:
        return CandidateMove.model_validate({**candidate_data, "rank": rank})

    move_uci = item.get("moveUci")
    if not isinstance(move_uci, str) or len(move_uci) < 4:
        return None

    simplicity = int(item.get("beginnerSimplicityScore") or 72)
    risk_penalty = int(item.get("tacticalRisk") or 12)
    coach_score = int(item.get("finalCoachScore") or item.get("planFitScore") or 76)
    engine_score = int(item.get("engineScore") or 70)
    summary = str(item.get("purpose") or item.get("pedagogicalExplanation") or "Coup naturel qui respecte le plan choisi.")

    return CandidateMove(
        rank=rank,
        moveUci=move_uci,
        moveSan=str(item.get("moveSan") or move_uci),
        stockfishRank=int(item.get("engineRank") or 99),
        evalCp=None,
        mateIn=None,
        pv=[move_uci],
        coachScore=coach_score,
        engineScore=engine_score,
        humanLikelihood=max(50, min(100, round((simplicity + coach_score) / 2))),
        simplicityScore=simplicity,
        riskPenalty=risk_penalty,
        difficulty=difficulty_for_complexity(str(item.get("moveComplexity") or "simple"), simplicity, risk_penalty),
        risk=risk_for_penalty(risk_penalty),
        summary=summary,
    )


def difficulty_for_complexity(complexity: str, simplicity: int, risk_penalty: int) -> str:
    if complexity == "complexe" or risk_penalty >= 35 or simplicity < 50:
        return "hard"
    if complexity == "moyen" or risk_penalty >= 20 or simplicity < 70:
        return "medium"
    return "easy"


def risk_for_penalty(risk_penalty: int) -> str:
    if risk_penalty >= 36:
        return "high"
    if risk_penalty >= 19:
        return "medium"
    return "low"


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
