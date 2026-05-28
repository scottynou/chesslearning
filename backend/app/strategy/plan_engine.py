from __future__ import annotations

import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import chess

logger = logging.getLogger(__name__)

# Pool partage pour lancer Stockfish + Maia en parallele dans la meme
# requete. Maia + Stockfish n'ont pas de dependance entre eux : on peut
# economiser la latence de Maia (200-500ms) en les overlappant.
_parallel_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="plan-parallel")

MAIA_BONUS_MAX = 25.0
MAIA_CRISIS_DISABLE_THRESHOLD = 0.20
ELO_COMPARISON_LEVELS = (800, 1500, 2000, 3000)
PROFILE_REFERENCE_ELO = {
    "beginner": 800,
    "lambda": 1500,
    "strong": 2000,
    "veryStrong": 3000,
}

from ..ai_reranker import rerank_recommendations
from ..accuracy_math import score_to_expected_percent
from ..beginner_notation import beginner_notation_for_uci
from ..elo_ranker import rank_candidates
from ..evaluation_label import evaluation_label
from ..maia_engine import get_engine as get_maia_engine, is_enabled as maia_is_enabled
from ..pv_translator import simple_move_explanation
from ..stockfish_engine import EngineLine, StockfishEngine
from ..winrate_service import get_winrate
from .endgame_coach import analyze_endgame
from .middlegame_coach import analyze_middlegame
from .move_merger import merge_plan_and_engine_moves
from .scoring_profile import (
    accuracy_bands_for_profile,
    coach_style_modifiers,
    compute_crisis_factor,
)

# Alias retrocompatible : les tests historiques referencent ce nom.
def accuracy_bands_for_elo(elo: int) -> dict[str, dict[str, int]]:
    """DEPRECATED : utiliser accuracy_bands_for_profile(human_profile, elo)."""
    return accuracy_bands_for_profile(None, elo)
from .opening_coach import (
    detect_current_opening,
    detect_transposition,
    explain_opening_status,
    get_next_plan_steps,
    get_opponent_deviation,
    get_plan,
    suggest_adaptation_after_deviation,
)
from .phase_detector import detect_game_phase


def get_plan_recommendations(
    fen: str,
    selected_plan_id: str | None,
    elo: int,
    move_history: list[str],
    skill_level: str | None = None,
    human_profile: str | None = None,
    coach_style: str = "balanced",
    max_moves: int = 10,
    engine_depth: int = 10,
    user_side: str | None = None,
    include_elo_comparisons: bool = True,
) -> dict[str, Any]:
    board = chess.Board(fen)
    selected_plan = get_plan(selected_plan_id)
    detected_plan = detect_current_opening(move_history)
    transposed_plan = detect_transposition(move_history)
    active_plan = selected_plan or detected_plan or transposed_plan
    locked_plan = selected_plan is not None

    phase = detect_game_phase(fen, move_history, plan_active=active_plan is not None)
    status = compute_status(active_plan, selected_plan, move_history, phase)
    deviation = get_opponent_deviation(active_plan["id"], move_history) if active_plan else None
    raw_plan_moves = get_next_plan_steps(active_plan["id"], move_history) if active_plan and phase == "opening" else []
    plan_moves = [move for move in raw_plan_moves if _is_legal_uci(board, move)]
    plan_color = color_for_plan(active_plan)
    if plan_color is None:
        plan_color = color_for_side(user_side)
    game_over = board.is_game_over()
    opponent_turn = not game_over and plan_color is not None and board.turn != plan_color
    player_turn = not game_over and not opponent_turn
    level_settings = skill_level_settings(skill_level, elo, max_moves)
    engine_profile = engine_search_profile_for_elo(elo, level_settings)

    plan_can_drive_opening = phase == "opening" and status == "on_plan" and bool(plan_moves)
    # Maia est lance en parallele de Stockfish (s'il est actif et qu'on
    # est en mode joueur). Pas de dependance entre les deux : on les fait
    # en concurrent pour gagner ~200-500ms de latence.
    maia_future = (
        _parallel_executor.submit(_maia_probabilities_for_fen, fen, elo, human_profile)
        if player_turn and not game_over and not plan_can_drive_opening and maia_is_enabled()
        else None
    )

    if game_over:
        engine_lines = []
        engine_candidates = []
    else:
        safety_window = int(engine_profile["safetyWindow"])
        multipv = int(engine_profile["multipv"])
        recommend_ms = int(engine_profile["movetimeMs"])
        critical_ms = int(engine_profile["criticalMovetimeMs"])
        effective_engine_depth = max(engine_depth, int(engine_profile["minDepth"]))
        try:
            engine_lines = StockfishEngine().analyze(fen, multipv=multipv, depth=effective_engine_depth, movetime_ms=recommend_ms)
            engine_candidates = rank_candidates(fen, engine_lines, elo=elo, max_moves=safety_window)
        except Exception:
            if not plan_can_drive_opening:
                raise
            engine_lines = []
            engine_candidates = []
        if (
            critical_ms > recommend_ms
            and engine_candidates
            and (
                mate_danger_from_side_to_move(engine_candidates) == "critical"
                or score_from_side_to_move(engine_candidates) <= -260
                or side_to_move_expected_percent_for_candidates(engine_candidates) <= 38.0
            )
        ):
            try:
                engine_lines = StockfishEngine().analyze(fen, multipv=multipv, depth=effective_engine_depth, movetime_ms=critical_ms)
                engine_candidates = rank_candidates(fen, engine_lines, elo=elo, max_moves=safety_window)
            except Exception:
                if not plan_can_drive_opening:
                    raise
    merged = merge_plan_and_engine_moves(
        fen=fen,
        plan_moves=plan_moves,
        engine_candidates=engine_candidates,
        engine_lines=engine_lines,
        plan_name=active_plan.get("nameFr") if active_plan else None,
        elo=elo,
        current_step_index=len(move_history),
    )

    plan_items = [item for item in merged if item["source"] in {"plan", "plan_and_engine"}]
    expected_opponent_move = (
        pure_engine_expected_opponent_move(fen, max(engine_depth, 14), _int_env("STOCKFISH_EXPECTED_MS", 650))
        if opponent_turn
        else None
    )
    visible_plan_items = [] if opponent_turn else plan_items
    visible_merged = [] if opponent_turn else merged
    primary_move = None if opponent_turn else choose_primary_move(visible_plan_items, visible_merged)
    if player_turn and primary_move is None and not game_over:
        visible_merged = fallback_legal_recommendations(
            board=board,
            plan_name=active_plan.get("nameFr") if active_plan else None,
            phase=phase,
            limit=int(level_settings["technical_limit"]),
        )
        primary_move = choose_primary_move([], visible_merged)
    phase_status = phase_status_for(
        board=board,
        plan=active_plan,
        status=status,
        move_history=move_history,
        primary_move=primary_move,
    )
    opening_state = opening_state_for(
        board=board,
        plan=active_plan,
        status=status,
        phase=phase,
        phase_status=phase_status,
        move_history=move_history,
        plan_moves=plan_moves,
        primary_move=primary_move,
        deviation=deviation,
    )
    if opening_state == "completed":
        phase = "middlegame"
        status = "plan_completed"
        phase_status = "opening_success"
        visible_plan_items = []
        strategic_pool = [item for item in visible_merged if item["source"] == "engine"] or visible_merged
        primary_move = choose_primary_move([], strategic_pool)
    elif opening_state == "abandoned" and phase == "opening":
        phase = "middlegame"
        phase_status = "fallback"
        visible_plan_items = []
        visible_merged = [item for item in visible_merged if item["source"] != "plan"] or visible_merged
        primary_move = choose_primary_move([], visible_merged)
        if player_turn and primary_move is None and not game_over:
            visible_merged = fallback_legal_recommendations(
                board=board,
                plan_name=active_plan.get("nameFr") if active_plan else None,
                phase=phase,
                limit=int(level_settings["technical_limit"]),
            )
            primary_move = choose_primary_move([], visible_merged)

    phase_display = phase_display_for(phase, phase_status)
    opponent_strength = opponent_move_strength_for(
        move_history=move_history,
        player_color=plan_color,
        player_turn=player_turn,
        engine_depth=engine_depth,
    )
    position_score = score_from_side_to_move(engine_candidates)
    mating_danger = mate_danger_from_side_to_move(engine_candidates)
    side_to_move_expected = side_to_move_expected_percent_for_candidates(engine_candidates)
    accuracy_profile = accuracy_profile_for(
        board=board,
        phase_display=phase_display,
        phase_status=phase_status,
        opening_state=opening_state,
        engine_candidates=engine_candidates,
        move_history=move_history,
        player_turn=player_turn,
        opponent_strength=opponent_strength,
        elo=elo,
        human_profile=human_profile,
    )
    elite_selection_boost = elite_selection_boost_for(
        elo=elo,
        mode=str(accuracy_profile.get("mode", "normal")),
        position_score=position_score,
        mating_danger=mating_danger,
        opponent_strength=opponent_strength,
        draw_pressure=accuracy_profile.get("drawPressure"),
        side_to_move_expected_percent=side_to_move_expected,
    )
    crisis_factor_value = float(accuracy_profile.get("crisisFactor") or 0.0)
    if maia_future is not None and crisis_factor_value <= MAIA_CRISIS_DISABLE_THRESHOLD and engine_candidates:
        try:
            maia_probabilities = maia_future.result(timeout=4.0)
        except Exception:  # noqa: BLE001
            maia_probabilities = {}
    else:
        if maia_future is not None:
            maia_future.cancel()
        maia_probabilities = {}
    accuracy_profile = {
        **accuracy_profile,
        "targetElo": elo,
        "eliteHumanization": elo >= 2800,
        "humanizationMode": elite_selection_mode_for(elite_selection_boost) if elo >= 2800 else "standard",
        "eliteSelectionBoost": elite_selection_boost,
        "eliteSelectionMode": elite_selection_mode_for(elite_selection_boost),
        "positionScore": position_score,
        "sideToMoveExpectedPercent": side_to_move_expected,
        "matingDanger": mating_danger,
        "humanSeed": human_seed_for(fen, move_history),
        "fen": fen,
        "phaseKey": phase_display["key"],
        "phaseStatus": phase_status,
        "openingState": opening_state,
        "coachStyle": coach_style,
        "styleModifiers": coach_style_modifiers(coach_style),
        "maiaProbabilities": maia_probabilities,
        "openingSafetyMode": should_apply_opening_safety(
            phase_display=phase_display,
            phase_status=phase_status,
            opening_state=opening_state,
            move_history=move_history,
            player_turn=player_turn,
            position_score=position_score,
            mating_danger=mating_danger,
        ),
    }
    logger.info(
        "plan_recommendations profile=%s style=%s elo=%s mode=%s crisis=%.2f bands=%s/%s/%s draw=%s mating=%s pos=%scp expected=%.1f",
        accuracy_profile.get("humanProfile"),
        accuracy_profile.get("coachStyle"),
        elo,
        accuracy_profile.get("mode"),
        float(accuracy_profile.get("crisisFactor") or 0.0),
        accuracy_profile.get("min"),
        accuracy_profile.get("target"),
        accuracy_profile.get("max"),
        (accuracy_profile.get("drawPressure") or {}).get("level"),
        mating_danger,
        position_score,
        side_to_move_expected,
    )
    strong_human_profile = strong_human_profile_for(accuracy_profile, opponent_strength)
    survival_shaping = float(accuracy_profile.get("crisisFactor") or 0.0) > 0.0 or str(accuracy_profile.get("mode")) in {"pressure", "survival", "draw_break"}
    if player_turn and visible_merged and (should_shape_for_human_accuracy(phase_display, phase_status, opening_state) or survival_shaping):
        visible_merged = shape_recommendations_for_accuracy(visible_merged, accuracy_profile)
        primary_move = choose_primary_move([], visible_merged)
    visible_recommendations = visible_recommendations_for(
        phase_display=phase_display,
        primary_move=primary_move,
        merged=visible_merged,
    )
    ai_rerank_status = {
        "provider": "local",
        "model": None,
        "status": "disabled",
        "latencyMs": 0,
        "fallbackReason": "opponent_turn_or_no_visible_choices" if opponent_turn else "not_enough_choices",
    }
    if player_turn and visible_recommendations and not game_over:
        if accuracy_profile.get("eliteHumanization"):
            ai_rerank_status = {
                "provider": "local",
                "model": None,
                "status": "disabled",
                "latencyMs": 0,
                "fallbackReason": "elite_humanization_local_only",
            }
        else:
            visible_recommendations, ai_rerank_status = rerank_recommendations(
                fen=fen,
                selected_plan=active_plan,
                phase=phase,
                opening_state=opening_state,
                move_history=move_history,
                recommendations=visible_recommendations,
                strong_human_profile=strong_human_profile,
            )
        if should_shape_for_human_accuracy(phase_display, phase_status, opening_state) or survival_shaping:
            visible_recommendations = shape_recommendations_for_accuracy(visible_recommendations, accuracy_profile)
        visible_recommendations = decorate_recommendations(
            visible_recommendations,
            str(phase_display["recommendationStyle"]),
        )
    primary_move = visible_recommendations[0] if visible_recommendations else None
    adapted_alternatives = visible_recommendations[1:]
    blocked_expected_move = blocked_expected_move_for(primary_move, deviation)
    if primary_move is not None:
        primary_move["movePlan"] = move_plan_for_recommendation(
            fen=fen,
            recommendation=primary_move,
            active_plan=active_plan,
            move_history=move_history,
        )
    adaptive_signal = adaptive_signal_for(
        primary_move=primary_move,
        phase_status=phase_status,
        blocked_expected_move=blocked_expected_move,
        opening_state=opening_state,
        player_turn=player_turn,
        engine_candidates=engine_candidates,
        draw_pressure=accuracy_profile.get("drawPressure"),
        opponent_strength=opponent_strength,
    )
    current_objective = current_objective_for(active_plan, phase, primary_move)
    progress = plan_progress_for(board, active_plan, move_history, phase_status)
    opening_brief = opening_brief_for(active_plan)
    technical_moves = [candidate.model_dump(by_alias=True) for candidate in engine_candidates[: int(engine_profile["technicalLimit"])]]
    coach_message = coach_message_for(active_plan, status, phase_status, locked_plan)
    last_event = last_event_for(move_history)
    what_changed = what_changed_for(active_plan, status, phase_status, deviation, primary_move)
    next_objective = current_objective
    phase_coach_context = phase_coach(fen, phase)
    strategic_plan = strategic_plan_for(
        plan=active_plan,
        phase=phase,
        opening_state=opening_state,
        current_objective=current_objective,
        what_changed=what_changed,
        coach_context=phase_coach_context,
        primary_move=primary_move,
        expected_opponent_move=expected_opponent_move,
    )
    plan_event = plan_event_for(active_plan, phase, opening_state, strategic_plan)
    phase_reason = phase_reason_for(phase, opening_state, active_plan, progress, phase_coach_context)
    pedagogical_summary = pedagogical_summary_for(coach_message, what_changed, next_objective)
    response_move_complexity = str(primary_move.get("moveComplexity", "simple")) if primary_move else "simple"
    position_win_rate = position_win_rate_for(
        board=board,
        engine_candidates=engine_candidates,
        user_side=user_side,
    )
    forced_mate = forced_mate_signal_for(board, engine_lines)
    elo_comparisons = (
        elo_comparisons_for(
            fen=fen,
            player_turn=player_turn,
            game_over=game_over,
            selected_reference_elo=reference_elo_for_profile(human_profile, elo),
            primary_move=primary_move,
            engine_lines=engine_lines,
            plan_moves=plan_moves,
            active_plan=active_plan,
            phase_display=phase_display,
            opening_state=opening_state,
            current_step_index=len(move_history),
            max_moves=int(engine_profile["safetyWindow"]),
        )
        if include_elo_comparisons
        else []
    )

    plan_state = {
        "selectedPlanId": active_plan.get("id") if active_plan else None,
        "planName": active_plan.get("nameFr") if active_plan else None,
            "side": active_plan.get("side") if active_plan else (user_side or ("white" if board.turn == chess.WHITE else "black")),
        "phase": phase,
        "status": status,
        "currentStepIndex": min(len(move_history), len(active_plan.get("mainLineUci", []))) if active_plan else 0,
        "currentGoals": active_plan.get("coreIdeas", [])[:3] if active_plan else fallback_goals(phase),
        "nextObjectives": next_objectives(active_plan, phase, visible_merged),
        "knownOpponentDeviation": deviation,
        "recommendedPlanMoves": [] if opponent_turn else plan_moves,
        "fallbackPrinciples": fallback_goals(phase),
        "engineSafetyWarning": next((item["warning"] for item in visible_merged if item.get("warning")), None),
        "statusExplanation": coach_message,
    }
    turn_context = {
        "sideToMove": "white" if board.turn == chess.WHITE else "black",
        "planSide": active_plan.get("side") if active_plan else user_side,
        "playerTurn": player_turn,
        "opponentTurn": opponent_turn,
        "gameOver": game_over,
    }

    return {
        "planState": plan_state,
        "planMoves": visible_plan_items[:1] if phase_display["key"] == "opening" else [],
        "engineMoves": technical_moves,
        "mergedRecommendations": visible_recommendations,
        "explanationContext": {
            "opening": active_plan,
            "detectedOpening": detected_plan,
            "transposition": transposed_plan if selected_plan and transposed_plan and transposed_plan["id"] != selected_plan["id"] else None,
            "adaptations": suggest_adaptation_after_deviation(fen, plan_state, engine_candidates),
            "phaseCoach": phase_coach_context,
            "skillLevel": level_settings,
            "accuracyProfile": accuracy_profile,
            "opponentStrength": opponent_strength,
            "strongHumanProfile": strong_human_profile,
        },
        "selectedPlan": active_plan,
        "phase": phase,
        "phaseDisplay": phase_display,
        "phaseStatus": phase_status,
        "openingState": opening_state,
        "phaseReason": phase_reason,
        "planEvent": plan_event,
        "strategicPlan": strategic_plan,
        "planProgress": progress,
        "openingBrief": opening_brief,
        "currentObjective": current_objective,
        "lastEvent": last_event,
        "whatChanged": what_changed,
        "nextObjective": next_objective,
        "recommendedPlanMoves": visible_recommendations,
        "primaryMove": primary_move,
        "expectedOpponentMove": expected_opponent_move,
        "adaptedAlternatives": adapted_alternatives,
        "blockedExpectedMove": blocked_expected_move,
        "coachMessage": coach_message,
        "pedagogicalSummary": pedagogical_summary,
        "moveComplexity": response_move_complexity,
        "turnContext": turn_context,
        "positionWinRate": position_win_rate,
        "forcedMate": forced_mate,
        "eloComparisons": elo_comparisons,
        "aiRerankStatus": ai_rerank_status,
        "adaptiveSignal": adaptive_signal,
        "technicalDetails": {
            "engineDepth": max(engine_depth, int(engine_profile["minDepth"])),
            "maxMoves": max_moves,
            "targetElo": elo,
            "accuracyBand": accuracy_profile.get("mode"),
            "selectionMode": engine_profile["selectionMode"],
            "humanizationMode": accuracy_profile.get("humanizationMode"),
            "eliteSelectionBoost": accuracy_profile.get("eliteSelectionBoost"),
            "eliteSelectionMode": accuracy_profile.get("eliteSelectionMode"),
            "selectedEngineRank": engine_rank_for(primary_move),
            "antiPerfectionApplied": anti_perfection_applied_for(primary_move, visible_merged, accuracy_profile),
            "openingSafetyMode": accuracy_profile.get("openingSafetyMode"),
            "humanSeed": accuracy_profile.get("humanSeed"),
            "multipv": engine_profile["multipv"],
            "movetimeMs": engine_profile["movetimeMs"],
            "detectedOpeningId": detected_plan.get("id") if detected_plan else None,
            "transpositionId": transposed_plan.get("id") if transposed_plan else None,
        },
        "technicalEngineMoves": technical_moves,
    }


def compute_status(active_plan: dict[str, Any] | None, selected_plan: dict[str, Any] | None, move_history: list[str], phase: str) -> str:
    if not active_plan:
        return "out_of_book"
    line = active_plan.get("mainLineUci", [])
    if phase in {"middlegame", "endgame", "transition"} and len(move_history) >= min(6, len(line)):
        return "plan_completed"
    if all(index < len(line) and move == line[index] for index, move in enumerate(move_history)):
        return "on_plan" if len(move_history) < len(line) else "plan_completed"
    if selected_plan and active_plan["id"] != selected_plan["id"]:
        return "transposed"
    return "opponent_deviated"


def fallback_goals(phase: str) -> list[str]:
    if phase == "opening":
        return ["Contrôler le centre.", "Développer les pièces mineures.", "Mettre le roi en sécurité."]
    if phase == "transition":
        return ["Finir le développement.", "Identifier une cible.", "Passer d'un coup de livre à un plan."]
    if phase == "middlegame":
        return ["Sécuriser le roi.", "Améliorer la pire pièce.", "Attaquer une faiblesse concrète."]
    return ["Activer le roi.", "Créer ou bloquer un pion passé.", "Simplifier si cela convertit l'avantage."]


def next_objectives(active_plan: dict[str, Any] | None, phase: str, merged: list[dict[str, Any]]) -> list[str]:
    if phase == "opening" and active_plan:
        objectives = active_plan.get("coreIdeas", [])[:2]
        if merged:
            objectives.append(str(merged[0]["purpose"]))
        return objectives[:4]
    if phase == "middlegame" and active_plan:
        return active_plan.get("middlegamePlan", fallback_goals(phase))[:4]
    if phase == "endgame" and active_plan:
        return active_plan.get("endgamePlan", fallback_goals(phase))[:4]
    return fallback_goals(phase)


def phase_coach(fen: str, phase: str) -> dict[str, Any]:
    if phase == "middlegame":
        return analyze_middlegame(fen)
    if phase == "endgame":
        return analyze_endgame(fen)
    if phase == "transition":
        return {
            "phase": "Transition",
            "mainGoal": "Quitter la mémorisation et choisir un objectif de milieu de jeu.",
            "currentPriorities": fallback_goals("transition"),
            "candidatePlans": [],
        }
    return {
        "phase": "Ouverture",
        "mainGoal": "Construire le plan choisi avec des coups simples et coherents.",
        "currentPriorities": fallback_goals("opening"),
        "candidatePlans": [],
    }


def skill_level_settings(skill_level: str | None, elo: int, max_moves: int) -> dict[str, Any]:
    level = skill_level or ("beginner" if elo < 1700 else "intermediate" if elo < 2400 else "pro")
    if level == "pro":
        return {"id": "pro", "label": "Pro", "alternative_limit": 4, "technical_limit": min(10, max(max_moves, 5))}
    if level == "intermediate":
        return {"id": "intermediate", "label": "Intermédiaire", "alternative_limit": 3, "technical_limit": min(8, max(max_moves, 4))}
    return {"id": "beginner", "label": "Débutant", "alternative_limit": 2, "technical_limit": min(5, max(max_moves, 3))}


def engine_search_profile_for_elo(elo: int, level_settings: dict[str, Any]) -> dict[str, Any]:
    base_limit = int(level_settings["technical_limit"])
    if elo >= 2800:
        technical_limit = min(10, max(base_limit, 8))
        return {
            "selectionMode": "elite_human_practical",
            "technicalLimit": technical_limit,
            "safetyWindow": min(10, max(technical_limit, 10)),
            "multipv": 30,
            "movetimeMs": _int_env("STOCKFISH_ELITE_RECOMMEND_MS", 1200),
            "criticalMovetimeMs": _int_env("STOCKFISH_ELITE_CRITICAL_MS", 1800),
            "minDepth": 14,
        }
    if elo >= 1800:
        technical_limit = min(9, max(base_limit, 6))
        return {
            "selectionMode": "strong_human",
            "technicalLimit": technical_limit,
            "safetyWindow": min(10, max(technical_limit, 8)),
            "multipv": 24,
            "movetimeMs": _int_env("STOCKFISH_STRONG_RECOMMEND_MS", 850),
            "criticalMovetimeMs": _int_env("STOCKFISH_STRONG_CRITICAL_MS", 1300),
            "minDepth": 10,
        }
    technical_limit = min(6, max(base_limit, 4))
    return {
        "selectionMode": "solid_human",
        "technicalLimit": technical_limit,
        "safetyWindow": min(8, max(technical_limit, 6)),
        "multipv": 16,
        "movetimeMs": _int_env("STOCKFISH_SOLID_RECOMMEND_MS", 650),
        "criticalMovetimeMs": _int_env("STOCKFISH_SOLID_CRITICAL_MS", 1100),
        "minDepth": 8,
    }


def choose_primary_move(plan_items: list[dict[str, Any]], merged: list[dict[str, Any]]) -> dict[str, Any] | None:
    safe_plan_items = [item for item in plan_items if not _is_severe_warning(item)]
    if safe_plan_items:
        return sorted(safe_plan_items, key=lambda item: item.get("planRank") or 99)[0]
    return merged[0] if merged else None


def color_for_plan(plan: dict[str, Any] | None) -> chess.Color | None:
    if not plan:
        return None
    if plan.get("side") == "white":
        return chess.WHITE
    if plan.get("side") == "black":
        return chess.BLACK
    return None


def color_for_side(side: str | None) -> chess.Color | None:
    if side == "white":
        return chess.WHITE
    if side == "black":
        return chess.BLACK
    return None


def color_for_ply_index(index: int) -> chess.Color:
    return chess.WHITE if index % 2 == 0 else chess.BLACK


def opening_brief_for(plan: dict[str, Any] | None) -> dict[str, str]:
    if not plan:
        return {
            "summary": "Le plan consiste a jouer des coups simples : centre, pieces actives, roi en securite.",
            "completion": "L'ouverture est terminee quand le roi est en securite, les pieces sortent et le centre est clair.",
        }
    name = str(plan.get("nameFr") or "Cette ouverture")
    goal = str(plan.get("learningGoal") or plan.get("beginnerGoal") or "installer une position claire.")
    transition = plan.get("transitionToMiddlegame", {}) if isinstance(plan.get("transitionToMiddlegame"), dict) else {}
    when = [str(item) for item in transition.get("when", []) if item]
    if when:
        completion = "Terminee lorsque " + ", ".join(when[:2]) + "."
    else:
        criteria = [str(item) for item in plan.get("successCriteria", []) if item]
        completion = criteria[0] if criteria else "Terminee lorsque le centre, le developpement et la securite du roi sont traites."
    return {
        "summary": f"{name} consiste a {goal[0].lower() + goal[1:] if goal else 'installer une position claire.'}",
        "completion": completion,
    }


def progress_impact_for(plan: dict[str, Any], move_history: list[str], plan_color: chess.Color | None, percent: int) -> str:
    if not move_history:
        return "La progression demarre au premier coup utile du plan."
    last_index = len(move_history) - 1
    last_side = color_for_ply_index(last_index)
    if percent >= 82:
        return "L'ouverture est presque terminee : les derniers coups doivent surtout stabiliser la position."
    if plan_color is not None and last_side != plan_color:
        return "Le coup adverse ne valide pas directement ton ouverture : le coach adapte le prochain repere."
    line = plan.get("mainLineUci", [])
    last_move = move_history[-1]
    if last_index < len(line) and line[last_index] == last_move:
        return "Ce coup fait avancer la ligne principale de l'ouverture."
    if last_move in line:
        return "Ce coup reste lie au plan, meme si l'ordre de coups a change."
    return "Ce coup garde la position jouable, mais il avance moins directement l'ouverture choisie."


def phase_display_for(phase: str, phase_status: str) -> dict[str, Any]:
    display_phase = "middlegame" if phase in {"transition", "middlegame"} or phase_status == "opening_success" else phase
    if display_phase == "endgame":
        return {
            "key": "endgame",
            "label": "Finale",
            "subtitle": "Un seul coup utile, clair et fort.",
            "recommendationStyle": "single",
            "maxVisibleMoves": 1,
        }
    if display_phase == "middlegame":
        return {
            "key": "middlegame",
            "label": "Milieu de partie",
            "subtitle": "Un seul coup utile, clair et fort.",
            "recommendationStyle": "single",
            "maxVisibleMoves": 1,
        }
    return {
        "key": "opening",
        "label": "Ouverture",
        "subtitle": "Un seul coup pour accomplir ton plan.",
        "recommendationStyle": "single",
        "maxVisibleMoves": 1,
    }


def visible_recommendations_for(
    phase_display: dict[str, Any],
    primary_move: dict[str, Any] | None,
    merged: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not primary_move:
        return []
    return decorate_recommendations([primary_move], str(phase_display["recommendationStyle"]))


def decorate_recommendations(items: list[dict[str, Any]], style: str) -> list[dict[str, Any]]:
    labels = {
        "single": ["Coup recommande"],
        "ranked": ["Coup recommande"],
        "conversion": ["Coup recommande"],
    }.get(style, ["Coup recommande"])
    colors = ["rgba(224,185,118,0.78)"]
    decorated = []
    for index, item in enumerate(items):
        copy = dict(item)
        copy["displayRank"] = index + 1
        copy["displayRole"] = labels[min(index, len(labels) - 1)]
        copy["arrowColor"] = colors[min(index, len(colors) - 1)]
        decorated.append(copy)
    return decorated


def move_plan_for_recommendation(
    *,
    fen: str,
    recommendation: dict[str, Any],
    active_plan: dict[str, Any] | None,
    move_history: list[str],
) -> dict[str, Any] | None:
    move_uci = str(recommendation.get("moveUci") or "")
    if not move_uci:
        return None

    engine_line = engine_pv_for_recommendation(recommendation)
    plan_line = opening_line_for_recommendation(active_plan, move_history, move_uci)
    line_source = "engine_pv" if len(engine_line) >= 2 else "opening_plan" if len(plan_line) >= 2 else "principle"
    raw_line = engine_line if line_source == "engine_pv" else plan_line if line_source == "opening_plan" else [move_uci]
    steps = move_plan_steps(fen, raw_line, max_plies=5)
    if not steps:
        return None

    summary = clean_move_plan_sentence(
        str(recommendation.get("purpose") or recommendation.get("planConnection") or steps[0].get("idea") or "")
    )
    if not summary:
        summary = "Ce coup ameliore la position et prepare la suite naturelle."

    branches = move_plan_branches(steps)
    compact_line = compact_move_plan_line(branches, steps, summary)
    depth = len(steps)

    return {
        "title": "Plan du coup",
        "summary": summary,
        "compactLine": compact_line,
        "source": line_source,
        "depth": depth,
        "steps": steps,
        "branches": branches,
    }


def engine_pv_for_recommendation(recommendation: dict[str, Any]) -> list[str]:
    move_uci = str(recommendation.get("moveUci") or "")
    candidate = recommendation.get("candidate")
    pv = candidate.get("pv") if isinstance(candidate, dict) else None
    line = [str(move) for move in pv if isinstance(move, str)] if isinstance(pv, list) else []
    if not move_uci:
        return line[:5]
    if not line:
        return [move_uci]
    if line[0] != move_uci:
        line = [move_uci, *[move for move in line if move != move_uci]]
    return line[:5]


def opening_line_for_recommendation(active_plan: dict[str, Any] | None, move_history: list[str], move_uci: str) -> list[str]:
    if not active_plan:
        return [move_uci]

    main_line = [str(move) for move in active_plan.get("mainLineUci", []) if isinstance(move, str)]
    if len(main_line) > len(move_history) and main_line[: len(move_history)] == move_history:
        remaining = main_line[len(move_history) :]
        if remaining and remaining[0] == move_uci:
            return remaining[:5]

    for branch in active_plan.get("branches", []):
        if not isinstance(branch, dict):
            continue
        trigger = [str(move) for move in branch.get("triggerLineUci", []) if isinstance(move, str)]
        recommended = [str(move) for move in branch.get("recommendedMoves", []) if isinstance(move, str)]
        candidate_line = trigger + recommended
        if len(candidate_line) > len(move_history) and candidate_line[: len(move_history)] == move_history:
            remaining = candidate_line[len(move_history) :]
            if remaining and remaining[0] == move_uci:
                return remaining[:5]

    return [move_uci]


def move_plan_steps(fen: str, raw_line: list[str], max_plies: int) -> list[dict[str, Any]]:
    board = chess.Board(fen)
    side_to_move = board.turn
    steps: list[dict[str, Any]] = []

    for ply_index, move_uci in enumerate(raw_line[:max_plies]):
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            break
        if move not in board.legal_moves:
            break

        san = board.san(move)
        notation = beginner_notation_for_uci(board.fen(), move_uci, san)
        actor = "you" if board.turn == side_to_move else "opponent"
        steps.append(
            {
                "ply": ply_index + 1,
                "actor": actor,
                "moveUci": move_uci,
                "label": notation.beginner_label,
                "shortLabel": notation.short_label,
                "idea": clean_move_plan_sentence(simple_move_explanation(board, move)),
            }
        )
        board.push(move)

    return steps


def move_plan_branches(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    branches: list[dict[str, str]] = []
    # The first step is the recommended move. Then pairs of opponent reply / our answer.
    for index in range(1, min(len(steps) - 1, 4), 2):
        condition = steps[index]
        response = steps[index + 1]
        if condition.get("actor") != "opponent" or response.get("actor") != "you":
            continue
        branches.append(
            {
                "ifLabel": str(condition.get("label") or ""),
                "thenLabel": str(response.get("label") or ""),
                "goal": str(response.get("idea") or "continuer le plan sans perdre de temps."),
            }
        )
    return branches[:2]


def compact_move_plan_line(branches: list[dict[str, str]], steps: list[dict[str, Any]], summary: str) -> str:
    if branches:
        first = branches[0]
        return f"Si {first['ifLabel']}, alors {first['thenLabel']}"
    if len(steps) >= 2:
        return f"Suite naturelle : {steps[1]['label']}"
    return summary


def clean_move_plan_sentence(value: str) -> str:
    text = " ".join(value.strip().split())
    if not text:
        return ""
    return text[0].upper() + text[1:]


def reference_elo_for_profile(human_profile: str | None, elo: int) -> int:
    if human_profile in PROFILE_REFERENCE_ELO:
        return PROFILE_REFERENCE_ELO[human_profile]
    return min(ELO_COMPARISON_LEVELS, key=lambda level: abs(level - elo))


def elo_comparisons_for(
    *,
    fen: str,
    player_turn: bool,
    game_over: bool,
    selected_reference_elo: int,
    primary_move: dict[str, Any] | None,
    engine_lines: list[Any],
    plan_moves: list[str],
    active_plan: dict[str, Any] | None,
    phase_display: dict[str, Any],
    opening_state: str,
    current_step_index: int,
    max_moves: int,
) -> list[dict[str, Any]]:
    if game_over or not player_turn:
        return []

    comparison_plan_moves = (
        plan_moves
        if phase_display.get("key") == "opening" and opening_state not in {"completed", "abandoned"}
        else []
    )
    plan_name = active_plan.get("nameFr") if active_plan else None
    comparisons: list[dict[str, Any]] = []

    for comparison_elo in ELO_COMPARISON_LEVELS:
        is_active = comparison_elo == selected_reference_elo
        if is_active and primary_move is not None:
            item = primary_move
        elif not engine_lines and primary_move is not None:
            item = primary_move
        else:
            candidates = rank_candidates(fen, engine_lines, elo=comparison_elo, max_moves=max_moves)
            merged = merge_plan_and_engine_moves(
                fen=fen,
                plan_moves=comparison_plan_moves,
                engine_candidates=candidates,
                engine_lines=engine_lines,
                plan_name=plan_name,
                elo=comparison_elo,
                current_step_index=current_step_index,
            )
            plan_items = [item for item in merged if item["source"] in {"plan", "plan_and_engine"}]
            item = choose_primary_move(plan_items, merged)

        if item is not None:
            comparisons.append(elo_comparison_payload(comparison_elo, is_active, item))

    return comparisons


def elo_comparison_payload(elo: int, active: bool, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "elo": elo,
        "label": str(elo),
        "active": active,
        "moveUci": str(item.get("moveUci") or ""),
        "moveSan": str(item.get("moveSan") or ""),
        "beginnerLabel": str(item.get("beginnerLabel") or item.get("moveSan") or item.get("moveUci") or ""),
        "source": str(item.get("source") or "engine"),
        "engineRank": item.get("engineRank"),
        "engineScore": item.get("engineScore"),
        "finalCoachScore": item.get("finalCoachScore"),
        "moveComplexity": item.get("moveComplexity"),
        "warning": item.get("warning"),
    }


def should_shape_for_human_accuracy(phase_display: dict[str, Any], phase_status: str, opening_state: str) -> bool:
    if phase_display["key"] != "opening":
        return True
    return phase_status in {"adapted", "fallback"} or opening_state in {"recoverable", "abandoned"}


def should_apply_opening_safety(
    *,
    phase_display: dict[str, Any],
    phase_status: str,
    opening_state: str,
    move_history: list[str],
    player_turn: bool,
    position_score: int,
    mating_danger: str,
) -> bool:
    if not player_turn or phase_display.get("key") != "opening":
        return False
    if len(move_history) > 12 or mating_danger == "critical" or position_score <= -90:
        return False
    return phase_status in {"fallback", "adapted"} or opening_state in {"recoverable", "abandoned"}


def accuracy_profile_for(
    *,
    board: chess.Board,
    phase_display: dict[str, Any],
    phase_status: str,
    opening_state: str,
    engine_candidates: list[Any],
    move_history: list[str],
    player_turn: bool,
    opponent_strength: dict[str, Any] | None = None,
    elo: int = 1600,
    human_profile: str | None = None,
) -> dict[str, Any]:
    draw_pressure = draw_pressure_for(
        board=board,
        phase_display=phase_display,
        move_history=move_history,
        engine_candidates=engine_candidates,
    )
    bands = accuracy_bands_for_profile(human_profile, elo)
    resolved_profile = human_profile or ("beginner" if elo < 1100 else "lambda" if elo < 1700 else "strong" if elo < 2600 else "veryStrong")
    base_opponent = opponent_strength or {"level": "none", "suggestedBoostDelta": 0}

    if not player_turn:
        return {
            "mode": "idle",
            **bands["normal"],
            "reason": "Hors tour joueur.",
            "drawPressure": draw_pressure,
            "humanProfile": resolved_profile,
            "crisisFactor": 0.0,
        }

    position_score = score_from_side_to_move(engine_candidates)
    mating_danger = mate_danger_from_side_to_move(engine_candidates)
    side_to_move_expected = side_to_move_expected_percent_for_candidates(engine_candidates)
    phase_key = str(phase_display.get("key", "opening"))
    opponent_delta = int((opponent_strength or {}).get("suggestedBoostDelta") or 0)
    opponent_level = str((opponent_strength or {}).get("level", "none"))
    planless_opening_fallback = phase_key == "opening" and phase_status == "fallback" and opening_state == "recoverable"

    crisis_factor = compute_crisis_factor(
        position_score,
        mating_danger,
        draw_pressure,
        side_to_move_expected_percent=side_to_move_expected,
    )

    def _build(mode: str, band_key: str, reason: str) -> dict[str, Any]:
        selected = bands[band_key]
        if crisis_factor > 0.0 and band_key != "survival":
            survival = bands["survival"]
            f = crisis_factor
            selected = {
                "target": round(selected["target"] * (1.0 - f) + survival["target"] * f),
                "min": round(selected["min"] * (1.0 - f) + survival["min"] * f),
                "max": round(selected["max"] * (1.0 - f) + survival["max"] * f),
                "planTolerance": round(selected["planTolerance"] * (1.0 - f) + survival.get("planTolerance", 0) * f),
            }
        return {
            "mode": mode,
            **selected,
            "reason": reason,
            "drawPressure": draw_pressure,
            "opponentStrength": base_opponent,
            "humanProfile": resolved_profile,
            "crisisFactor": crisis_factor,
            "sideToMoveExpectedPercent": side_to_move_expected,
        }

    if mating_danger == "critical" or side_to_move_expected <= 30.0 or position_score <= -320:
        return _build("survival", "survival", "Position critique : le meilleur coup moteur est autorise sans penalite.")
    if side_to_move_expected <= 38.0 or position_score <= -220:
        return _build("pressure", "elite_pressure", "Risque de defaite eleve : le coach depasse le profil initial pour sauver la partie.")
    if side_to_move_expected <= 44.0:
        return _build("pressure", "strong_pressure", "La probabilite de perte devient trop haute : precision renforcee.")
    if draw_pressure["level"] == "critical":
        return _build("draw_break", "draw_critical", "La position devient trop nulle : on cherche des coups precis qui gardent des chances de gain.")
    if (opponent_delta >= 200 or opponent_level == "elite") and (side_to_move_expected <= 46.0 or planless_opening_fallback is False and phase_status in {"adapted", "fallback"}):
        return _build("pressure", "elite_pressure", "L'adversaire joue proche de Stockfish : les conseils montent vers un humain tres fort.")
    if (opponent_delta >= 150 or opponent_level == "strong") and side_to_move_expected <= 48.0:
        return _build("pressure", "strong_pressure", "L'adversaire joue tres precis : le ranking devient plus exigeant tout de suite.")
    if phase_status == "adapted" or opening_state == "abandoned" or (phase_status == "fallback" and not planless_opening_fallback) or position_score <= -90:
        return _build("pressure", "pressure", "Sous pression : on choisit un coup humain fort, pas un compromis mou.")
    if draw_pressure["level"] == "warning":
        return _build("draw_break", "draw_warning", "Risque de simplification vers nulle : on augmente la precision pour garder du jeu.")
    if phase_key == "endgame":
        return _build("conversion", "conversion", "Finale : les coups doivent convertir proprement sans laisser filer la victoire.")
    if position_score >= 220:
        return _build("normal", "favorable", "Position favorable : on convertit activement au lieu de relacher vers la nulle.")
    return _build("normal", "normal", "Humain fort : viser la victoire avec un coup sain, pas forcement le top moteur automatique.")


# accuracy_bands_for_profile a ete deplace dans scoring_profile.py


def _maia_level_for_profile(human_profile: str | None, elo: int) -> int:
    """Mappe le profil humain vers le poids Maia le plus proche."""
    if human_profile in {"beginner", "lambda"}:
        return 1500
    if human_profile == "veryStrong":
        return 1900
    if human_profile == "strong":
        return 1900
    if elo < 1700:
        return 1500
    if elo < 2200:
        return 1900
    return 1900


def _maia_probabilities_for_fen(fen: str, elo: int, human_profile: str | None) -> dict[str, float]:
    """
    Lance Maia sur une position et retourne {move_uci: probability}.
    Utilise par le thread parallele dans get_plan_recommendations.
    """
    level = _maia_level_for_profile(human_profile, elo)
    try:
        engine = get_maia_engine(level)
        suggestions = engine.suggest(fen, top_n=18)
    except Exception:  # noqa: BLE001
        return {}
    return {move.move_uci: move.probability for move in suggestions}


# coach_style_modifiers et compute_crisis_factor ont ete deplaces dans scoring_profile.py


def elite_selection_boost_for(
    *,
    elo: int,
    mode: str,
    position_score: int,
    mating_danger: str,
    opponent_strength: dict[str, Any] | None,
    draw_pressure: dict[str, Any] | None,
    side_to_move_expected_percent: float | None = None,
) -> int:
    if elo < 2800:
        return 0

    opponent_delta = int((opponent_strength or {}).get("suggestedBoostDelta") or 0)
    opponent_level = str((opponent_strength or {}).get("level", "none"))
    draw_level = str((draw_pressure or {}).get("level", "none"))
    expected = 50.0 if side_to_move_expected_percent is None else float(side_to_move_expected_percent)
    if mating_danger == "critical" or mode == "survival" or expected <= 30.0 or position_score <= -260:
        return 3
    if expected <= 38.0 or draw_level == "critical" or opponent_level == "elite" or opponent_delta >= 200 or position_score <= -160:
        return 2
    if expected <= 44.0 or mode in {"pressure", "draw_break"} or opponent_level == "strong" or opponent_delta >= 150 or position_score <= -90:
        return 1
    return 0


def elite_selection_mode_for(boost: int) -> str:
    if boost >= 3:
        return "gm_survival"
    if boost == 2:
        return "gm_precision"
    if boost == 1:
        return "gm_guard"
    return "gm_practical"


def strong_human_profile_for(profile: dict[str, Any], opponent_strength: dict[str, Any] | None) -> dict[str, Any]:
    mode = str(profile.get("mode", "normal"))
    if mode not in {"normal", "pressure", "draw_break", "survival"}:
        mode = "pressure" if mode == "conversion" else "normal"
    return {
        "mode": mode,
        "targetMin": int(profile.get("min", 90)),
        "targetMax": int(profile.get("max", 94)),
        "opponentStrength": opponent_strength or {"level": "none", "suggestedBoostDelta": 0},
        "drawPressure": profile.get("drawPressure", {"level": "none"}),
    }


def draw_pressure_for(
    *,
    board: chess.Board,
    phase_display: dict[str, Any],
    move_history: list[str],
    engine_candidates: list[Any],
) -> dict[str, Any]:
    score = score_from_side_to_move(engine_candidates)
    abs_score = abs(score)
    phase_key = str(phase_display.get("key", "opening"))
    piece_map = board.piece_map()
    piece_count = len(piece_map)
    pawns = sum(1 for piece in piece_map.values() if piece.piece_type == chess.PAWN)
    queens = sum(1 for piece in piece_map.values() if piece.piece_type == chess.QUEEN)
    major_pieces = sum(1 for piece in piece_map.values() if piece.piece_type in {chess.QUEEN, chess.ROOK})
    candidate_spread = candidate_score_spread(engine_candidates[:5])
    low_spread = candidate_spread <= 40
    very_low_spread = candidate_spread <= 24
    ply_count = len(move_history)
    minor_pieces = sum(1 for piece in piece_map.values() if piece.piece_type in {chess.BISHOP, chess.KNIGHT})

    base = {
        "level": "none",
        "reason": "Pas de signal de nulle.",
        "scoreCp": score,
        "spreadCp": candidate_spread,
        "pieceCount": piece_count,
        "pawns": pawns,
        "queens": queens,
        "majorPieces": major_pieces,
        "minorPieces": minor_pieces,
    }

    if board.is_insufficient_material():
        return {**base, "level": "critical", "reason": "Materiel insuffisant : la partie tend deja vers nulle."}
    if board.halfmove_clock >= 86:
        return {**base, "level": "critical", "reason": "Regle des 50 coups proche : il faut creer une rupture utile."}
    if board.halfmove_clock >= 64:
        return {**base, "level": "warning", "reason": "La position stagne depuis longtemps : il faut creer une rupture."}
    if phase_key == "endgame" and abs_score <= 60 and (queens == 0 or pawns <= 6):
        return {**base, "level": "critical", "reason": "Finale tres egale avec peu de materiel."}
    if phase_key == "endgame" and abs_score <= 105:
        return {**base, "level": "warning", "reason": "Finale encore jouable mais trop proche de l'egalite."}
    if ply_count >= 18 and queens == 0 and major_pieces <= 4 and abs_score <= 75:
        return {**base, "level": "critical", "reason": "Les dames sont sorties et l'evaluation reste trop plate."}
    if ply_count >= 12 and queens == 0 and abs_score <= 120:
        return {**base, "level": "warning", "reason": "Echange des dames avec peu d'avantage : risque de nulle rapide."}
    if ply_count >= 20 and piece_count <= 18 and abs_score <= 110:
        return {**base, "level": "warning", "reason": "Le materiel baisse sans avantage clair : il faut jouer plus ambitieux."}
    if ply_count >= 16 and abs_score <= 35 and low_spread:
        return {**base, "level": "critical", "reason": "Position trop egale et peu de differences entre les coups moteur."}
    if ply_count >= 10 and abs_score <= 55 and very_low_spread:
        return {**base, "level": "warning", "reason": "La partie devient deja trop plate : il faut augmenter la precision."}
    if ply_count >= 26 and abs_score <= 65 and low_spread:
        return {**base, "level": "warning", "reason": "Les meilleurs coups se valent trop : risque de partie plate."}
    return base


def candidate_score_spread(engine_candidates: list[Any]) -> int:
    scores = [getattr(candidate, "eval_cp", None) for candidate in engine_candidates]
    numeric_scores = [int(score) for score in scores if score is not None]
    if len(numeric_scores) < 2:
        return 999
    return max(numeric_scores) - min(numeric_scores)


def shape_recommendations_for_accuracy(items: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    if len(items) <= 1:
        return [annotate_accuracy(dict(item), profile) for item in items]

    mode = str(profile.get("mode", "normal"))
    if mode == "survival":
        ordered = sorted(
            items,
            key=lambda item: (
                -int(item.get("engineScore") or 0),
                int(item.get("tacticalRisk") or 0),
                -int(item.get("finalCoachScore") or 0),
                item.get("engineRank") or 99,
            ),
        )
        return [annotate_accuracy(dict(item), profile) for item in ordered]

    candidates = [item for item in items if not _is_severe_warning(item)]
    if not candidates:
        candidates = list(items)

    minimum = int(profile.get("min", 78))
    plan_tolerance = int(profile.get("planTolerance", 4))
    competitive_floor = competitive_human_engine_floor(candidates, profile)
    if elite_humanization_enabled(profile):
        viable = elite_viable_candidates(candidates, profile)
    else:
        viable = [
            item
            for item in candidates
            if int(item.get("engineScore") or 0) >= max(minimum, competitive_floor)
            or (
                plan_tolerance > 0
                and int(item.get("planFitScore") or 0) >= 90
                and int(item.get("engineScore") or 0) >= max(minimum - plan_tolerance, competitive_floor)
                and int(item.get("tacticalRisk") or 0) <= 22
            )
        ]
    if not viable:
        viable = sorted(candidates, key=lambda item: -int(item.get("engineScore") or 0))[: max(1, min(3, len(candidates)))]

    selection_profile = {
        **profile,
        "antiPerfectionAvailable": elite_practical_alternative_exists(viable, profile),
    }
    ordered = sorted(viable, key=lambda item: human_accuracy_sort_score(item, selection_profile), reverse=True)
    remaining = [
        item
        for item in candidates
        if item.get("moveUci") not in {ordered_item.get("moveUci") for ordered_item in ordered}
    ]
    tail = sorted(
        remaining,
        key=lambda item: (
            -int(item.get("engineScore") or 0),
            int(item.get("tacticalRisk") or 0),
            -int(item.get("finalCoachScore") or 0),
        ),
    )
    return [annotate_accuracy(dict(item), profile) for item in [*ordered, *tail]]


def human_profile_from_scoring_profile(profile: dict[str, Any]) -> str:
    explicit = profile.get("humanProfile")
    if explicit in {"beginner", "lambda", "strong", "veryStrong"}:
        return str(explicit)

    target = int(profile.get("target") or 79)
    if target <= 73:
        return "beginner"
    if target <= 80:
        return "lambda"
    if target < 87:
        return "strong"
    return "veryStrong"


def competitive_human_engine_floor(candidates: list[dict[str, Any]], profile: dict[str, Any]) -> int:
    if not candidates:
        return 0

    top_score = max(int(item.get("engineScore") or 0) for item in candidates)
    mode = str(profile.get("mode", "normal"))
    if mode == "survival":
        return top_score

    human_profile = human_profile_from_scoring_profile(profile)
    if mode in {"pressure", "draw_break"}:
        acceptable_drop = 12
    elif mode == "conversion":
        acceptable_drop = 14
    elif human_profile == "beginner":
        acceptable_drop = 24
    elif human_profile == "lambda":
        acceptable_drop = 18
    elif human_profile == "strong":
        acceptable_drop = 16
    else:
        acceptable_drop = 14

    crisis_factor = max(0.0, min(1.0, float(profile.get("crisisFactor") or 0.0)))
    effective_drop = round(acceptable_drop * (1.0 - crisis_factor) + 8 * crisis_factor)
    return max(0, min(100, top_score - effective_drop))


def human_accuracy_sort_score(item: dict[str, Any], profile: dict[str, Any]) -> float:
    engine_score = int(item.get("engineScore") or 0)
    plan_fit = int(item.get("planFitScore") or 0)
    simplicity = int(item.get("beginnerSimplicityScore") or 0)
    risk = int(item.get("tacticalRisk") or 0)
    final_score = int(item.get("finalCoachScore") or 0)
    target = int(profile.get("target", 92))
    minimum = int(profile.get("min", 90))
    maximum = int(profile.get("max", 94))
    mode = str(profile.get("mode", "normal"))
    plan_tolerance = int(profile.get("planTolerance", 4))
    elite_humanization = elite_humanization_enabled(profile)
    elite_selection_boost = int(profile.get("eliteSelectionBoost") or 0)
    human_profile = human_profile_from_scoring_profile(profile)
    crisis_factor = float(profile.get("crisisFactor") or 0.0)

    if elite_humanization and elite_selection_boost >= 3:
        over_penalty = 0.02
        under_penalty = 9.0
        distance_penalty = 0.22
        weights = (0.68, 0.06, 0.02, 0.24)
    elif elite_humanization and elite_selection_boost == 2:
        over_penalty = 0.05
        under_penalty = 7.2
        distance_penalty = 0.35
        weights = (0.58, 0.10, 0.03, 0.24)
    elif elite_humanization and elite_selection_boost == 1:
        over_penalty = 0.08
        under_penalty = 5.8
        distance_penalty = 0.50
        weights = (0.48, 0.14, 0.05, 0.22)
    elif elite_humanization and mode == "normal":
        over_penalty = 1.85
        under_penalty = 5.4
        distance_penalty = 1.12
        weights = (0.24, 0.26, 0.14, 0.24)
    elif elite_humanization and mode == "conversion":
        over_penalty = 1.20
        under_penalty = 5.0
        distance_penalty = 0.95
        weights = (0.30, 0.20, 0.10, 0.24)
    elif human_profile == "beginner" and mode in {"normal", "favorable", "comfortable"}:
        # Niveau 800 : prefere les coups naturels et lisibles, tout en gardant
        # un plancher moteur pour eviter les vraies gaffes.
        base_over, base_distance = 2.15, 1.70
        base_weights = (0.20, 0.25, 0.17, 0.12)
        f = crisis_factor
        over_penalty = base_over * (1.0 - f) + 0.10 * f
        under_penalty = 4.8
        distance_penalty = base_distance * (1.0 - f) + 0.34 * f
        weights = tuple(b * (1.0 - f) + c * f for b, c in zip(base_weights, (0.72, 0.07, 0.02, 0.20)))
    elif human_profile == "beginner" and mode == "conversion":
        f = crisis_factor
        over_penalty = 1.25 * (1.0 - f) + 0.08 * f
        under_penalty = 4.8
        distance_penalty = 1.15 * (1.0 - f) + 0.30 * f
        weights = tuple(b * (1.0 - f) + c * f for b, c in zip((0.27, 0.22, 0.12, 0.15), (0.70, 0.07, 0.02, 0.20)))
    elif human_profile == "lambda" and mode in {"normal", "favorable", "comfortable"}:
        # Niveau lambda : fort biais vers coups sous-optimaux, évite le meilleur coup
        base_over, base_distance = 1.55, 1.30
        base_weights = (0.28, 0.20, 0.11, 0.16)
        # Débridage progressif : vers précision moteur en cas de crise
        f = crisis_factor
        over_penalty = base_over * (1.0 - f) + 0.08 * f
        under_penalty = 5.0
        distance_penalty = base_distance * (1.0 - f) + 0.30 * f
        weights = tuple(b * (1.0 - f) + c * f for b, c in zip(base_weights, (0.72, 0.07, 0.02, 0.20)))
    elif human_profile == "lambda" and mode == "conversion":
        f = crisis_factor
        over_penalty = 0.95 * (1.0 - f) + 0.06 * f
        under_penalty = 5.0
        distance_penalty = 0.95 * (1.0 - f) + 0.28 * f
        weights = tuple(b * (1.0 - f) + c * f for b, c in zip((0.34, 0.17, 0.08, 0.18), (0.70, 0.07, 0.02, 0.20)))
    elif human_profile == "strong" and mode in {"normal", "favorable", "comfortable"}:
        # Niveau strong : évitement modéré du meilleur coup
        f = crisis_factor
        over_penalty = 1.15 * (1.0 - f) + 0.10 * f
        under_penalty = 4.3
        distance_penalty = 1.05 * (1.0 - f) + 0.32 * f
        weights = tuple(b * (1.0 - f) + c * f for b, c in zip((0.31, 0.20, 0.08, 0.18), (0.68, 0.08, 0.03, 0.21)))
    elif human_profile == "strong" and mode == "conversion":
        f = crisis_factor
        over_penalty = 0.55 * (1.0 - f) + 0.08 * f
        under_penalty = 4.2
        distance_penalty = 0.78 * (1.0 - f) + 0.30 * f
        weights = tuple(b * (1.0 - f) + c * f for b, c in zip((0.35, 0.15, 0.07, 0.22), (0.68, 0.08, 0.02, 0.20)))
    elif mode == "draw_break":
        f = crisis_factor
        over_penalty = 0.10 * (1.0 - f) + 0.04 * f
        under_penalty = 4.8
        distance_penalty = 0.55 * (1.0 - f) + 0.20 * f
        weights = (0.34, 0.16, 0.06, 0.24)
    elif mode == "pressure":
        f = crisis_factor
        over_penalty = 0.16 * (1.0 - f) + 0.04 * f
        under_penalty = 4.6
        distance_penalty = 0.70 * (1.0 - f) + 0.22 * f
        weights = (0.36, 0.17, 0.07, 0.21)
    elif mode == "conversion":
        over_penalty = 0.55
        under_penalty = 4.2
        distance_penalty = 0.78
        weights = (0.35, 0.15, 0.07, 0.22)
    elif mode == "comfortable":
        over_penalty = 1.30
        under_penalty = 4.0
        distance_penalty = 0.95
        weights = (0.31, 0.18, 0.08, 0.19)
    else:
        over_penalty = 1.15
        under_penalty = 4.3
        distance_penalty = 1.05
        weights = (0.31, 0.20, 0.08, 0.18)

    in_band_bonus = 26 if minimum <= engine_score <= maximum else 0
    engine_rank = engine_rank_for(item) or 99
    anti_perfection_available = bool(profile.get("antiPerfectionAvailable"))
    if elite_humanization and elite_selection_boost >= 3:
        top_engine_bonus = {1: 38, 2: 16}.get(engine_rank, 0)
    elif elite_humanization and elite_selection_boost == 2:
        top_engine_bonus = {1: 26, 2: 16, 3: 8}.get(engine_rank, 0)
    elif elite_humanization and elite_selection_boost == 1:
        top_engine_bonus = {1: 16, 2: 11, 3: 6, 4: 2}.get(engine_rank, 0)
    elif elite_humanization and anti_perfection_available and mode in {"normal", "conversion"}:
        top_engine_bonus = 0
    elif mode in {"pressure", "draw_break"}:
        top_engine_bonus = 8 if engine_rank == 1 and engine_score >= minimum else 0
    elif mode == "conversion":
        top_engine_bonus = 5 if engine_rank == 1 and minimum <= engine_score <= maximum else 0
    else:
        top_engine_bonus = 4 if engine_rank == 1 and minimum <= engine_score <= maximum else 0
    elite_practical_bonus = elite_practical_bonus_for(
        engine_rank=engine_rank,
        engine_score=engine_score,
        plan_fit=plan_fit,
        simplicity=simplicity,
        risk=risk,
        profile=profile,
    )
    plan_bonus = (
        10
        if item.get("source") in {"plan", "plan_and_engine"}
        and plan_tolerance > 0
        and engine_score >= minimum - plan_tolerance
        and risk <= 22
        else 0
    )
    anti_perfection_penalty = anti_perfection_penalty_for(
        engine_rank=engine_rank,
        engine_score=engine_score,
        profile=profile,
    )
    style_mods = profile.get("styleModifiers") or coach_style_modifiers(str(profile.get("coachStyle") or "balanced"))
    # En crise (>0.5), on attenue progressivement les modulateurs de style :
    # l'objectif devient gagner/ne pas perdre, pas exprimer un style.
    style_strength = max(0.0, 1.0 - max(0.0, crisis_factor - 0.4) / 0.6)
    risk_multiplier = 0.50 + (float(style_mods.get("risk_mul", 0.50)) - 0.50) * style_strength
    simplicity_style_bonus = float(style_mods.get("simplicity_bonus", 0.0)) * style_strength
    distance_relax = float(style_mods.get("distance_relax", 0.0)) * style_strength
    creative_rank_bonus_value = float(style_mods.get("creative_rank_bonus", 0.0)) * style_strength
    creative_rank_bonus = (
        creative_rank_bonus_value
        if creative_rank_bonus_value > 0 and 2 <= engine_rank <= 5 and minimum <= engine_score <= maximum and risk <= 28
        else 0.0
    )
    effective_distance_penalty = max(0.0, distance_penalty * (1.0 - distance_relax))

    # Bonus Maia : si Maia connait ce coup avec une forte probabilite, on le
    # favorise. C'est l'apport "vraiment humain" : Maia a vu des humains
    # jouer ce coup dans des positions similaires. Attenue en crise pour ne
    # pas contrarier la survie.
    maia_probs = profile.get("maiaProbabilities") or {}
    move_uci = str(item.get("moveUci") or "")
    maia_prob = float(maia_probs.get(move_uci, 0.0))
    # Bonus proportionnel a la proba (25 max), tempere par la crise, gele
    # si le coup serait en dessous du minimum d'accuracy (pas de gaffe humaine).
    maia_bonus = (
        maia_prob * MAIA_BONUS_MAX * style_strength
        if maia_prob > 0 and engine_score >= minimum - 4
        else 0.0
    )

    return (
        in_band_bonus
        + top_engine_bonus
        + elite_practical_bonus
        + plan_bonus
        + creative_rank_bonus
        + maia_bonus
        + final_score * weights[3]
        + plan_fit * weights[1]
        + simplicity * (weights[2] + simplicity_style_bonus)
        + engine_score * weights[0]
        + opening_safety_adjustment_for(item, profile)
        + draw_avoidance_bonus(item, profile)
        + elite_crisis_adjustment_for(item, profile)
        + (0.0 if elite_selection_boost > 0 else deterministic_human_variation(item, profile))
        - risk * risk_multiplier
        - abs(engine_score - target) * effective_distance_penalty
        - max(0, minimum - engine_score) * under_penalty
        - max(0, engine_score - maximum) * over_penalty
        - anti_perfection_penalty
    )


def elite_humanization_enabled(profile: dict[str, Any]) -> bool:
    return bool(profile.get("eliteHumanization")) or int(profile.get("targetElo") or 0) >= 2800


def opening_safety_adjustment_for(item: dict[str, Any], profile: dict[str, Any]) -> float:
    if not profile.get("openingSafetyMode"):
        return 0.0
    fen = str(profile.get("fen") or "")
    move_uci = str(item.get("moveUci") or "")
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        return 0.0
    if move not in board.legal_moves:
        return 0.0

    piece = board.piece_at(move.from_square)
    if piece is None:
        return 0.0

    target_elo = int(profile.get("targetElo") or 1500)
    strictness = 1.0 if target_elo < 1800 else 0.72 if target_elo < 2600 else 0.38
    bonus = 0.0
    penalty = 0.0
    to_square = chess.square_name(move.to_square)
    from_square = chess.square_name(move.from_square)
    gives_check = board.gives_check(move)
    is_capture = board.is_capture(move)

    if board.is_castling(move):
        bonus += 34
    if _is_canonical_first_opening_move(board, move):
        bonus += 40
    if piece.piece_type == chess.PAWN and to_square in {"d4", "e4", "d5", "e5"}:
        bonus += 30
    elif piece.piece_type == chess.PAWN and to_square in {"c4", "c5"}:
        bonus += 20
    if _is_natural_opening_development(board, move, piece):
        bonus += 26
    if piece.piece_type in {chess.KNIGHT, chess.BISHOP} and chess.square_file(move.to_square) in {0, 7}:
        penalty += 46
    if piece.piece_type == chess.PAWN and from_square[0] in {"a", "h"} and not is_capture and not gives_check:
        penalty += 42
    if piece.piece_type == chess.PAWN and from_square[0] == "f" and not is_capture and not gives_check:
        penalty += 32
    if piece.piece_type == chess.QUEEN and board.fullmove_number <= 8 and not is_capture and not gives_check:
        penalty += 26
    if item.get("source") in {"plan", "plan_and_engine"}:
        bonus += 18
    if is_capture and int(item.get("tacticalRisk") or 0) <= 18:
        bonus += 8

    return bonus - penalty * strictness


def _is_natural_opening_development(board: chess.Board, move: chess.Move, piece: chess.Piece) -> bool:
    if piece.piece_type not in {chess.KNIGHT, chess.BISHOP}:
        return False
    home_rank = 0 if piece.color == chess.WHITE else 7
    if chess.square_rank(move.from_square) != home_rank or board.fullmove_number > 12:
        return False
    to_file = chess.square_file(move.to_square)
    if to_file in {0, 7}:
        return False
    return True


def _is_canonical_first_opening_move(board: chess.Board, move: chess.Move) -> bool:
    if board.fullmove_number != 1:
        return False
    if board.turn == chess.WHITE:
        return move.uci() in {"e2e4", "d2d4", "c2c4", "g1f3"}
    return move.uci() in {"e7e5", "d7d5", "c7c5", "g8f6"}


def elite_viable_candidates(candidates: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    minimum = int(profile.get("min", 86))
    mode = str(profile.get("mode", "normal"))
    hard_floor = [item for item in candidates if int(item.get("engineScore") or 0) >= minimum]
    if not hard_floor:
        return []

    boost = int(profile.get("eliteSelectionBoost") or 0)
    if boost > 0:
        rank_limit = 2 if boost >= 3 else 3 if boost == 2 else 4
        score_floor = max(minimum, 96 if boost >= 3 else 94 if boost == 2 else minimum)
        risk_ceiling = 26 if boost >= 3 else 30 if boost == 2 else 34
        strict = [
            item
            for item in hard_floor
            if (engine_rank_for(item) or 99) <= rank_limit
            and int(item.get("engineScore") or 0) >= score_floor
            and (int(item.get("tacticalRisk") or 0) <= risk_ceiling or engine_rank_for(item) == 1)
        ]
        if strict:
            return strict
        return sorted(
            hard_floor,
            key=lambda item: (
                engine_rank_for(item) or 99,
                -int(item.get("engineScore") or 0),
                int(item.get("tacticalRisk") or 0),
            ),
        )[: max(1, min(rank_limit, len(hard_floor)))]

    risk_ceiling = 45 if mode in {"pressure", "draw_break"} else 30 if mode == "conversion" else 34
    safe = [
        item
        for item in hard_floor
        if int(item.get("tacticalRisk") or 0) <= risk_ceiling
        or (mode in {"pressure", "draw_break"} and engine_rank_for(item) == 1)
    ]
    if safe:
        return safe

    return sorted(
        hard_floor,
        key=lambda item: (
            -int(item.get("engineScore") or 0),
            engine_rank_for(item) or 99,
            int(item.get("tacticalRisk") or 0),
        ),
    )[:1]


def elite_practical_alternative_exists(items: list[dict[str, Any]], profile: dict[str, Any]) -> bool:
    if not elite_humanization_enabled(profile) or str(profile.get("mode", "normal")) not in {"normal", "conversion"}:
        return False
    if int(profile.get("eliteSelectionBoost") or 0) > 0:
        return False

    top = next((item for item in items if engine_rank_for(item) == 1), None)
    if top is None:
        return False

    minimum = int(profile.get("min", 86))
    top_score = int(top.get("engineScore") or 0)
    mode = str(profile.get("mode", "normal"))
    acceptable_drop = 14 if mode == "normal" else 10
    for item in items:
        rank = engine_rank_for(item) or 99
        engine_score = int(item.get("engineScore") or 0)
        if (
            2 <= rank <= 6
            and engine_score >= minimum
            and engine_score >= top_score - acceptable_drop
            and int(item.get("tacticalRisk") or 0) <= 22
        ):
            return True
    return False


def elite_practical_bonus_for(
    *,
    engine_rank: int,
    engine_score: int,
    plan_fit: int,
    simplicity: int,
    risk: int,
    profile: dict[str, Any],
) -> float:
    if int(profile.get("eliteSelectionBoost") or 0) > 0:
        return 0.0
    minimum = int(profile.get("min", 90))
    maximum = int(profile.get("max", 94))
    mode = str(profile.get("mode", "normal"))
    if elite_humanization_enabled(profile) and mode in {"normal", "conversion"}:
        if not (2 <= engine_rank <= 6 and minimum <= engine_score <= maximum and risk <= 22):
            return 0.0
        rank_bonus = {2: 15, 3: 18, 4: 16, 5: 12, 6: 8}.get(engine_rank, 0)
        plan_bonus = 4 if plan_fit >= 70 else 0
        simplicity_bonus = 4 if simplicity >= 70 else 0
        return float(rank_bonus + plan_bonus + simplicity_bonus)
    if minimum >= 94 and 2 <= engine_rank <= 4 and minimum <= engine_score <= maximum and risk <= 18:
        return 7.0
    return 0.0


def elite_crisis_adjustment_for(item: dict[str, Any], profile: dict[str, Any]) -> float:
    if not elite_humanization_enabled(profile):
        return 0.0
    boost = int(profile.get("eliteSelectionBoost") or 0)
    if boost <= 0:
        return 0.0

    engine_rank = engine_rank_for(item) or 99
    engine_score = int(item.get("engineScore") or 0)
    risk = int(item.get("tacticalRisk") or 0)
    if boost >= 3:
        rank_bonus = {1: 54, 2: 22}.get(engine_rank, -70 if engine_rank > 2 else 0)
        return float(rank_bonus + engine_score * 0.22 - risk * 1.15 - max(0, risk - 18) * 1.6)
    if boost == 2:
        rank_bonus = {1: 32, 2: 20, 3: 10}.get(engine_rank, -36 if engine_rank > 3 else 0)
        return float(rank_bonus + engine_score * 0.13 - risk * 0.82 - max(0, risk - 22) * 1.1)

    rank_bonus = {1: 18, 2: 14, 3: 8, 4: 3}.get(engine_rank, -18 if engine_rank > 4 else 0)
    return float(rank_bonus + engine_score * 0.07 - risk * 0.62 - max(0, risk - 26) * 0.85)


def anti_perfection_penalty_for(*, engine_rank: int, engine_score: int, profile: dict[str, Any]) -> float:
    mode = str(profile.get("mode", "normal"))
    if (
        not elite_humanization_enabled(profile)
        or int(profile.get("eliteSelectionBoost") or 0) > 0
        or not profile.get("antiPerfectionAvailable")
        or mode not in {"normal", "conversion"}
        or engine_rank != 1
    ):
        return 0.0
    maximum = int(profile.get("max", 96))
    base = 18 if mode == "normal" else 10
    return float(base + max(0, engine_score - maximum) * 0.9)


def deterministic_human_variation(item: dict[str, Any], profile: dict[str, Any]) -> float:
    if not elite_humanization_enabled(profile) or str(profile.get("mode", "normal")) not in {"normal", "conversion"}:
        return 0.0
    if int(profile.get("eliteSelectionBoost") or 0) > 0:
        return 0.0
    seed = int(profile.get("humanSeed") or 0)
    move = str(item.get("moveUci") or "")
    digest = hashlib.sha256(f"{seed}:{move}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 2001
    return (bucket - 1000) / 1000.0 * 1.2


def human_seed_for(fen: str, move_history: list[str]) -> int:
    payload = f"{fen}|{' '.join(move_history)}"
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


def engine_rank_for(item: dict[str, Any] | None) -> int | None:
    if not item:
        return None
    value = item.get("engineRank")
    if value is None and isinstance(item.get("candidate"), dict):
        value = item["candidate"].get("stockfishRank")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def anti_perfection_applied_for(
    primary_move: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    profile: dict[str, Any],
) -> bool:
    if not elite_humanization_enabled(profile) or str(profile.get("mode", "normal")) not in {"normal", "conversion"}:
        return False
    if int(profile.get("eliteSelectionBoost") or 0) > 0:
        return False
    selected_rank = engine_rank_for(primary_move)
    if selected_rank is None or selected_rank == 1:
        return False
    return any(engine_rank_for(item) == 1 and int(item.get("engineScore") or 0) >= int(profile.get("min", 86)) for item in candidates)


def draw_avoidance_bonus(item: dict[str, Any], profile: dict[str, Any]) -> float:
    candidate_eval = candidate_eval_cp(item)
    engine_rank = item.get("engineRank") or 8
    tactical_risk = int(item.get("tacticalRisk") or 0)
    mode = str(profile.get("mode", "normal"))
    if mode == "draw_break":
        positive_eval_bonus = max(-60, min(260, candidate_eval)) * 0.14
        initiative_bonus = max(0, 8 - int(engine_rank)) * 1.7
        flat_penalty = 8 if abs(candidate_eval) <= 25 and int(engine_rank) <= 2 else 0
        risk_penalty = max(0, tactical_risk - 26) * 0.45
        return positive_eval_bonus + initiative_bonus - flat_penalty - risk_penalty
    if mode in {"normal", "pressure", "conversion"}:
        positive_eval_bonus = max(-30, min(180, candidate_eval)) * 0.035
        initiative_bonus = max(0, 5 - int(engine_rank)) * 0.75
        passive_penalty = 4 if abs(candidate_eval) <= 20 and int(profile.get("drawPressure", {}).get("spreadCp", 999)) <= 40 else 0
        return positive_eval_bonus + initiative_bonus - passive_penalty
    return 0.0


def candidate_eval_cp(item: dict[str, Any]) -> int:
    candidate = item.get("candidate")
    if isinstance(candidate, dict):
        value = candidate.get("evalCp")
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def candidate_mate_in(item: dict[str, Any]) -> int | None:
    candidate = item.get("candidate")
    if isinstance(candidate, dict):
        value = candidate.get("mateIn")
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def candidate_wdl(item: dict[str, Any]) -> list[int] | tuple[int, int, int] | None:
    candidate = item.get("candidate")
    if isinstance(candidate, dict):
        value = candidate.get("wdl")
        if isinstance(value, (list, tuple)) and len(value) == 3:
            try:
                return [int(part) for part in value]
            except (TypeError, ValueError):
                return None
    return None


def win_rate_estimate_for_item(item: dict[str, Any]) -> float:
    return round(
        score_to_expected_percent(
            eval_cp=candidate_eval_cp(item),
            mate_in=candidate_mate_in(item),
            wdl=candidate_wdl(item),
        ),
        1,
    )


def humanization_score_for_item(item: dict[str, Any], profile: dict[str, Any]) -> int:
    engine_score = int(item.get("engineScore") or 0)
    target = int(profile.get("target", 80))
    minimum = int(profile.get("min", 70))
    maximum = int(profile.get("max", 90))
    simplicity = int(item.get("beginnerSimplicityScore") or 0)
    plan_fit = int(item.get("planFitScore") or 0)
    risk = int(item.get("tacticalRisk") or 0)
    engine_rank = engine_rank_for(item) or 99
    coach_style = str(profile.get("coachStyle") or "balanced")

    band_fit = 100 - abs(engine_score - target) * 3
    if engine_score < minimum:
        band_fit -= (minimum - engine_score) * 5
    if engine_score > maximum:
        band_fit -= (engine_score - maximum) * 4

    if engine_rank == 1:
        rank_naturalness = 68
    elif 2 <= engine_rank <= 5:
        rank_naturalness = 95
    elif engine_rank <= 8:
        rank_naturalness = 82
    else:
        rank_naturalness = 64

    style_bonus = 0.0
    if coach_style == "creative" and 2 <= engine_rank <= 5:
        style_bonus += 5.0
    elif coach_style == "educational" and simplicity >= 76:
        style_bonus += 5.0
    elif coach_style == "solid" and risk <= 14:
        style_bonus += 4.0
    elif coach_style == "aggressive" and engine_score >= target and risk <= 32:
        style_bonus += 3.0

    score = (
        max(0, min(100, band_fit)) * 0.34
        + simplicity * 0.23
        + max(0, 100 - risk) * 0.15
        + rank_naturalness * 0.16
        + plan_fit * 0.10
        + style_bonus
    )
    return max(0, min(100, round(score)))


def annotate_accuracy(item: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    engine_score = int(item.get("engineScore") or 0)
    target = int(profile.get("target", 92))
    item["humanAccuracyEstimate"] = max(0, min(99, round(engine_score * 0.92 + target * 0.08)))
    item["accuracyBand"] = str(profile.get("mode", "normal"))
    item["winRateEstimate"] = win_rate_estimate_for_item(item)
    item["humanizationScore"] = humanization_score_for_item(item, profile)
    return item


def expected_opponent_move_for(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    copy = dict(item)
    copy["displayRank"] = 1
    copy["displayRole"] = "Coup adverse attendu"
    copy["arrowColor"] = "rgba(239,118,118,0.78)"
    return copy


def pure_engine_expected_opponent_move(fen: str, engine_depth: int, movetime_ms: int) -> dict[str, Any] | None:
    lines = StockfishEngine().analyze(fen, multipv=1, depth=engine_depth, movetime_ms=movetime_ms)
    candidates = rank_candidates(fen, lines, elo=3200, max_moves=1)
    if not candidates:
        return None
    return expected_opponent_move_for(recommendation_from_candidate(fen, candidates[0]))


def opponent_move_strength_for(
    *,
    move_history: list[str],
    player_color: chess.Color | None,
    player_turn: bool,
    engine_depth: int,
) -> dict[str, Any]:
    if not player_turn or player_color is None or not move_history:
        return {"level": "none", "suggestedBoostDelta": 0, "reason": "Pas de coup adverse a mesurer."}

    last_move_index = len(move_history) - 1
    last_move_color = chess.WHITE if last_move_index % 2 == 0 else chess.BLACK
    if last_move_color == player_color:
        return {"level": "none", "suggestedBoostDelta": 0, "reason": "Le dernier coup est un coup joueur."}

    previous_board = board_from_standard_history(move_history[:-1])
    if previous_board is None:
        return {"level": "unknown", "suggestedBoostDelta": 0, "reason": "Historique trop atypique pour mesurer le coup adverse."}

    try:
        move = chess.Move.from_uci(move_history[-1])
    except ValueError:
        return {"level": "unknown", "suggestedBoostDelta": 0, "reason": "Dernier coup adverse illisible."}
    if move not in previous_board.legal_moves:
        return {"level": "unknown", "suggestedBoostDelta": 0, "reason": "Dernier coup adverse non legal dans la position reconstruite."}

    strength_ms = _int_env("STOCKFISH_OPPONENT_STRENGTH_MS", 450)
    try:
        lines = StockfishEngine().analyze(
            previous_board.fen(),
            multipv=8,
            depth=max(engine_depth, 10),
            movetime_ms=strength_ms,
        )
    except Exception:
        return {"level": "unknown", "suggestedBoostDelta": 0, "reason": "Mesure Stockfish du coup adverse indisponible."}
    return opponent_move_strength_from_lines(move_history[-1], lines)


def opponent_move_strength_from_lines(move_uci: str, lines: list[Any]) -> dict[str, Any]:
    if not lines:
        return {"level": "unknown", "suggestedBoostDelta": 0, "reason": "Stockfish n'a pas pu mesurer le coup adverse."}

    scored = sorted(lines, key=engine_line_score, reverse=True)
    best_score = engine_line_score(scored[0])
    played_line = next((line for line in scored if getattr(line, "move_uci", None) == move_uci), None)
    if played_line is None:
        return {
            "level": "weak",
            "suggestedBoostDelta": 0,
            "reason": "Le coup adverse n'apparait pas dans les meilleurs choix Stockfish.",
        }

    played_score = engine_line_score(played_line)
    delta = max(0, best_score - played_score)
    rank = int(getattr(played_line, "stockfish_rank", 99) or 99)
    if rank == 1 or delta <= 20:
        return {
            "level": "elite",
            "suggestedBoostDelta": 200,
            "reason": "L'adversaire a joue quasiment le meilleur coup Stockfish : le niveau cache monte nettement.",
            "rank": rank,
            "deltaCp": delta,
        }
    if rank <= 3 or delta <= 55:
        return {
            "level": "strong",
            "suggestedBoostDelta": 150,
            "reason": "L'adversaire joue tres proche du moteur : le niveau cache monte.",
            "rank": rank,
            "deltaCp": delta,
        }
    if rank <= 6 or delta <= 110:
        return {
            "level": "good",
            "suggestedBoostDelta": 100,
            "reason": "L'adversaire joue un bon coup moteur : le niveau cache augmente progressivement.",
            "rank": rank,
            "deltaCp": delta,
        }
    return {
        "level": "normal",
        "suggestedBoostDelta": 50,
        "reason": "L'adversaire garde une qualite correcte : petit ajustement offensif.",
        "rank": rank,
        "deltaCp": delta,
    }


def board_from_standard_history(move_history: list[str]) -> chess.Board | None:
    board = chess.Board()
    for move_uci in move_history:
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            return None
        if move not in board.legal_moves:
            return None
        board.push(move)
    return board


def engine_line_score(line: Any) -> int:
    mate_in = getattr(line, "mate_in", None)
    if mate_in is not None:
        sign = 1 if mate_in > 0 else -1
        return sign * (100_000 - abs(int(mate_in)) * 1_000)
    eval_cp = getattr(line, "eval_cp", None)
    return int(eval_cp or 0)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def recommendation_from_candidate(fen: str, candidate) -> dict[str, Any]:
    notation = beginner_notation_for_uci(fen, candidate.move_uci, candidate.move_san)
    return {
        "moveUci": candidate.move_uci,
        "moveSan": notation.san,
        "beginnerLabel": notation.beginner_label,
        "source": "engine",
        "engineRank": candidate.stockfish_rank,
        "planRank": None,
        "planFitScore": 35,
        "engineScore": candidate.engine_score,
        "beginnerSimplicityScore": candidate.simplicity_score,
        "tacticalRisk": candidate.risk_penalty,
        "finalCoachScore": candidate.coach_score,
        "evalLabel": evaluation_label(candidate.eval_cp, candidate.mate_in),
        "purpose": candidate.summary,
        "planConnection": "Coup Stockfish pur attendu pour l'adversaire.",
        "pedagogicalExplanation": "",
        "moveComplexity": "simple" if candidate.difficulty == "easy" else "moyen" if candidate.difficulty == "medium" else "complexe",
        "warning": None,
        "candidate": candidate.model_dump(by_alias=True),
    }


def fallback_legal_recommendations(
    *,
    board: chess.Board,
    plan_name: str | None,
    phase: str,
    limit: int,
) -> list[dict[str, Any]]:
    fallback_moves = sorted(board.legal_moves, key=lambda move: fallback_move_score(board, move), reverse=True)
    recommendations = []
    for move in fallback_moves[: max(1, min(3, limit))]:
        move_uci = move.uci()
        notation = beginner_notation_for_uci(board.fen(), move_uci)
        purpose = purpose_for_fallback_move(board, move, phase)
        connection = (
            f"On sort de la ligne exacte de {plan_name}, donc le coach choisit un coup legal simple qui garde la position jouable."
            if plan_name
            else "Le coach choisit un coup legal simple qui respecte les principes de base."
        )
        recommendations.append(
            {
                "moveUci": move_uci,
                "moveSan": notation.san,
                "beginnerLabel": notation.beginner_label,
                "source": "fallback_principle",
                "engineRank": None,
                "planRank": None,
                "planFitScore": 35,
                "engineScore": 50,
                "beginnerSimplicityScore": 72,
                "tacticalRisk": 18,
                "finalCoachScore": 58,
                "evalLabel": "Coup legal simple",
                "purpose": purpose,
                "planConnection": connection,
                "pedagogicalExplanation": f"Joue {notation.beginner_label}. {purpose} {connection}",
                "moveComplexity": "simple",
                "warning": None,
                "candidate": None,
            }
        )
    return recommendations


def adaptive_signal_for(
    *,
    primary_move: dict[str, Any] | None,
    phase_status: str,
    blocked_expected_move: dict[str, Any] | None,
    opening_state: str,
    player_turn: bool,
    engine_candidates: list[Any],
    draw_pressure: dict[str, Any] | None = None,
    opponent_strength: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not player_turn:
        return {
            "pressure": "stable",
            "suggestedBoostDelta": 0,
            "reason": "L'ajustement attend ton tour pour eviter les sauts inutiles.",
        }
    if primary_move is None:
        return {
            "pressure": "stable",
            "suggestedBoostDelta": 0,
            "reason": "Aucun coup joueur actif a ajuster.",
        }

    warning = bool(blocked_expected_move)
    adapted = phase_status in {"adapted", "fallback"} or opening_state in {"recoverable", "abandoned"}
    position_score = score_from_side_to_move(engine_candidates)
    mating_danger = mate_danger_from_side_to_move(engine_candidates)
    side_to_move_expected = side_to_move_expected_percent_for_candidates(engine_candidates)
    draw_level = str((draw_pressure or {}).get("level", "none"))
    opponent_delta = int((opponent_strength or {}).get("suggestedBoostDelta") or 0)
    opponent_level = str((opponent_strength or {}).get("level", "none"))

    if mating_danger == "critical" or side_to_move_expected <= 24.0 or position_score <= -520:
        return {
            "pressure": "critical",
            "suggestedBoostDelta": 300,
            "reason": "La defaite devient tres probable : le coach debride fortement pour sauver la partie.",
        }
    if side_to_move_expected <= 32.0 or position_score <= -360:
        return {
            "pressure": "critical",
            "suggestedBoostDelta": 250,
            "reason": "Le risque de perte est trop haut : le coach depasse le profil initial.",
        }
    if side_to_move_expected <= 38.0 or position_score <= -260:
        return {
            "pressure": "critical",
            "suggestedBoostDelta": 200,
            "reason": "La partie tourne mal : priorite a ne pas perdre, meme si le coup est moins humain.",
        }
    if draw_level == "critical":
        return {
            "pressure": "drawish",
            "suggestedBoostDelta": 100,
            "reason": "La partie risque vraiment de finir nulle : le coach monte progressivement pour garder des chances de gain.",
        }
    if warning or side_to_move_expected <= 44.0 or position_score <= -180:
        return {
            "pressure": "worse",
            "suggestedBoostDelta": 150,
            "reason": "La probabilite de perte monte : le coach renforce les coups defensifs et pratiques.",
        }
    if opponent_delta >= 200 and (side_to_move_expected <= 46.0 or position_score <= -80 or adapted or draw_level in {"warning", "critical"}):
        return {
            "pressure": "worse",
            "suggestedBoostDelta": 100,
            "reason": "L'adversaire vient de jouer tres precisement dans une position qui demande deja de la vigilance.",
        }
    if opponent_delta >= 150 and (side_to_move_expected <= 48.0 or position_score <= -140):
        return {
            "pressure": "worse",
            "suggestedBoostDelta": 100,
            "reason": "L'adversaire joue proche des meilleurs coups pendant que la position glisse : le niveau cache suit doucement.",
        }
    if draw_level == "warning":
        return {
            "pressure": "drawish",
            "suggestedBoostDelta": 50,
            "reason": "La position devient trop egale : petit ajustement pour eviter une nulle passive.",
        }
    if opponent_delta >= 100 and adapted:
        return {
            "pressure": "worse",
            "suggestedBoostDelta": 50,
            "reason": "Le plan doit s'adapter apres un coup adverse precis : petit ajustement du niveau cache.",
        }
    if mating_danger == "warning" or position_score <= -180:
        return {
            "pressure": "worse",
            "suggestedBoostDelta": 100,
            "reason": "L'adversaire met une vraie pression : le niveau cache augmente pour rester dans la partie.",
        }
    if opponent_delta >= 150 and opponent_level != "weak":
        return {
            "pressure": "stable",
            "suggestedBoostDelta": 0,
            "reason": "L'adversaire joue precisement, mais la position reste saine : on surveille sans emballement.",
        }
    if position_score <= -90:
        return {
            "pressure": "worse",
            "suggestedBoostDelta": 50,
            "reason": "La position se degrade : petit ajustement pour ne pas subir.",
        }
    if position_score >= 420 and not warning:
        return {
            "pressure": "stable",
            "suggestedBoostDelta": -50,
            "reason": "La position est franchement confortable : le coach peut redescendre doucement.",
        }
    return {
        "pressure": "stable",
        "suggestedBoostDelta": 0,
        "reason": "Pas de changement utile du niveau cache.",
    }


def score_from_side_to_move(engine_candidates: list[Any]) -> int:
    if not engine_candidates:
        return 0
    candidate = top_stockfish_candidate(engine_candidates)
    eval_cp = getattr(candidate, "eval_cp", None)
    if eval_cp is None and isinstance(candidate, dict):
        eval_cp = candidate.get("evalCp")
    if eval_cp is None:
        return 0
    return int(eval_cp)


def side_to_move_expected_percent_for_candidates(engine_candidates: list[Any]) -> float:
    if not engine_candidates:
        return 50.0
    candidate = top_stockfish_candidate(engine_candidates)
    eval_cp = getattr(candidate, "eval_cp", None)
    mate_in = getattr(candidate, "mate_in", None)
    wdl = getattr(candidate, "wdl", None)
    if isinstance(candidate, dict):
        eval_cp = candidate.get("evalCp", eval_cp)
        mate_in = candidate.get("mateIn", mate_in)
        wdl = candidate.get("wdl", wdl)
    return side_to_move_win_percent(eval_cp, mate_in, wdl)


def forced_mate_signal_for(board: chess.Board, engine_lines: list[EngineLine]) -> dict[str, Any] | None:
    if board.is_game_over(claim_draw=True) or not engine_lines:
        return None

    top_line = min(engine_lines, key=lambda line: line.stockfish_rank)
    mate_in = top_line.mate_in
    if mate_in is None or mate_in <= 0 or mate_in > 3:
        return None

    try:
        move = chess.Move.from_uci(top_line.move_uci)
    except ValueError:
        return None
    if move not in board.legal_moves:
        return None

    side = "white" if board.turn == chess.WHITE else "black"
    return {
        "mateIn": int(mate_in),
        "side": side,
        "moveUci": top_line.move_uci,
        "moveSan": board.san(move),
        "label": f"Mat en {int(mate_in)}",
        "line": legal_prefix_for_pv(board, top_line.pv, max_plies=mate_in * 2 - 1),
        "lineSan": san_prefix_for_pv(board, top_line.pv, max_plies=mate_in * 2 - 1),
    }


def legal_prefix_for_pv(board: chess.Board, pv: list[str], max_plies: int) -> list[str]:
    clone = board.copy(stack=False)
    legal_line: list[str] = []
    for move_uci in pv[:max_plies]:
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            break
        if move not in clone.legal_moves:
            break
        legal_line.append(move_uci)
        clone.push(move)
    return legal_line


def san_prefix_for_pv(board: chess.Board, pv: list[str], max_plies: int) -> list[str]:
    clone = board.copy(stack=False)
    san_line: list[str] = []
    for move_uci in pv[:max_plies]:
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            break
        if move not in clone.legal_moves:
            break
        san_line.append(clone.san(move))
        clone.push(move)
    return san_line


def position_win_rate_for(
    *,
    board: chess.Board,
    engine_candidates: list[Any],
    user_side: str | None,
) -> dict[str, Any]:
    player_side = user_side if user_side in {"white", "black"} else ("white" if board.turn == chess.WHITE else "black")
    perspective = player_side if user_side in {"white", "black"} else "sideToMove"
    stockfish_line = top_stockfish_candidate(engine_candidates) if engine_candidates else None
    result = get_winrate(
        fen=board.fen(),
        perspective=perspective,  # type: ignore[arg-type]
        stockfish_line=stockfish_line,
        allow_stockfish=False,
    )
    white_win = result.white_winrate if result.white_winrate is not None else result.winrate
    black_win = result.black_winrate if result.black_winrate is not None else max(0.0, 100.0 - white_win)
    side_to_move_win = result.side_to_move_winrate
    if side_to_move_win is None:
        side_to_move_win = white_win if board.turn == chess.WHITE else black_win
    player_win = white_win if player_side == "white" else black_win
    eval_cp = getattr(stockfish_line, "eval_cp", None)
    mate_in = getattr(stockfish_line, "mate_in", None)
    wdl = getattr(stockfish_line, "wdl", None)
    if isinstance(stockfish_line, dict):
        eval_cp = stockfish_line.get("evalCp", eval_cp)
        mate_in = stockfish_line.get("mateIn", mate_in)
        wdl = stockfish_line.get("wdl", wdl)
    displayed_source = win_rate_source(eval_cp, mate_in, wdl) if result.source == "stockfish" else result.source
    return {
        "available": True,
        "playerSide": player_side,
        "perspective": "player" if user_side in {"white", "black"} else "side_to_move",
        "playerWinPercent": round(player_win, 1),
        "whiteWinPercent": round(white_win, 1),
        "blackWinPercent": round(black_win, 1),
        "sideToMoveWinPercent": round(side_to_move_win, 1),
        "evalCp": int(eval_cp) if eval_cp is not None else None,
        "mateIn": int(mate_in) if mate_in is not None else None,
        "sideToMoveWdl": normalize_wdl(wdl),
        "source": displayed_source,
        "confidence": result.confidence,
        "label": winrate_source_label(displayed_source, result.confidence),
    }


def side_to_move_win_percent(
    eval_cp: int | None,
    mate_in: int | None,
    wdl: list[int] | tuple[int, int, int] | None = None,
) -> float:
    return score_to_expected_percent(eval_cp=eval_cp, mate_in=mate_in, wdl=wdl)


def normalize_wdl(wdl: list[int] | tuple[int, int, int] | None) -> list[int] | None:
    if not wdl or len(wdl) != 3:
        return None
    try:
        return [max(0, int(value)) for value in wdl]
    except (TypeError, ValueError):
        return None


def win_rate_source(eval_cp: int | None, mate_in: int | None, wdl: list[int] | tuple[int, int, int] | None) -> str:
    if normalize_wdl(wdl) is not None:
        return "stockfish_wdl"
    if mate_in is not None:
        return "mate"
    if eval_cp is not None:
        return "centipawn"
    return "unavailable"


def position_win_rate_label(player_win_percent: float) -> str:
    if player_win_percent >= 80:
        return "Gros avantage"
    if player_win_percent >= 62:
        return "Avantage"
    if player_win_percent >= 54:
        return "Leger avantage"
    if player_win_percent > 46:
        return "Equilibre"
    if player_win_percent > 38:
        return "Leger retard"
    if player_win_percent > 20:
        return "Sous pression"
    return "Position critique"


def winrate_source_label(source: str, confidence: str) -> str:
    if source == "lichess_exact":
        base = "Donnees Lichess"
    elif source == "lichess_model":
        base = "Modele Lichess"
    elif source == "stockfish":
        base = "Estimation moteur"
    else:
        base = "Estimation simple"
    if confidence == "low":
        return f"{base} - confiance faible"
    return base


def mate_danger_from_side_to_move(engine_candidates: list[Any]) -> str:
    if not engine_candidates:
        return "none"
    candidate = top_stockfish_candidate(engine_candidates)
    mate_in = getattr(candidate, "mate_in", None)
    if mate_in is None and isinstance(candidate, dict):
        mate_in = candidate.get("mateIn")
    if mate_in is None:
        return "none"
    if mate_in < 0:
        return "critical"
    return "winning"


def top_stockfish_candidate(engine_candidates: list[Any]) -> Any:
    return min(engine_candidates, key=stockfish_rank_value)


def stockfish_rank_value(candidate: Any) -> int:
    if isinstance(candidate, dict):
        for key in ("stockfishRank", "stockfish_rank", "engineRank", "rank"):
            value = candidate.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 99
        return 99
    for attr in ("stockfish_rank", "stockfishRank", "engine_rank", "rank"):
        value = getattr(candidate, attr, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 99
    return 99


def fallback_move_score(board: chess.Board, move: chess.Move) -> int:
    piece = board.piece_at(move.from_square)
    if piece is None:
        return 0
    score = 0
    if board.is_castling(move):
        score += 60
    if board.is_capture(move):
        score += 35
    if board.gives_check(move):
        score += 25
    to_square = chess.square_name(move.to_square)
    if to_square in {"d4", "e4", "d5", "e5"}:
        score += 30
    home_rank = 0 if piece.color == chess.WHITE else 7
    if piece.piece_type in {chess.KNIGHT, chess.BISHOP} and chess.square_rank(move.from_square) == home_rank:
        score += 28
    if piece.piece_type == chess.QUEEN and board.fullmove_number <= 8:
        score -= 24
    return score


def purpose_for_fallback_move(board: chess.Board, move: chess.Move, phase: str) -> str:
    piece = board.piece_at(move.from_square)
    piece_name = beginner_notation_for_uci(board.fen(), move.uci()).piece_name
    to_square = chess.square_name(move.to_square)
    if board.is_castling(move):
        return "Le roque met le roi en securite et connecte les tours."
    if board.is_capture(move):
        return f"{piece_name} prend en {to_square} pour resoudre une tension concrete."
    if phase == "opening" and piece and piece.piece_type in {chess.KNIGHT, chess.BISHOP}:
        return f"{piece_name} va en {to_square} pour continuer le developpement."
    if to_square in {"d4", "e4", "d5", "e5"}:
        return f"{piece_name} va en {to_square} pour contester le centre."
    return f"{piece_name} va en {to_square} pour ameliorer la position sans forcer une variante compliquee."


def adapted_alternatives_for(
    merged: list[dict[str, Any]],
    primary_move: dict[str, Any] | None,
    status: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not primary_move or status == "on_plan":
        return []
    alternatives = [
        item
        for item in merged
        if item["moveUci"] != primary_move["moveUci"] and not _is_severe_warning(item)
    ]
    return alternatives[:limit]


def blocked_expected_move_for(primary_move: dict[str, Any] | None, deviation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not primary_move or not primary_move.get("warning"):
        return None
    return {
        "moveUci": primary_move["moveUci"],
        "beginnerLabel": primary_move["beginnerLabel"],
        "reason": primary_move["warning"],
        "deviation": deviation,
    }


def phase_status_for(
    board: chess.Board,
    plan: dict[str, Any] | None,
    status: str,
    move_history: list[str],
    primary_move: dict[str, Any] | None,
) -> str:
    if not plan:
        return "fallback"
    if status == "opponent_deviated":
        return "adapted"
    if status == "transposed":
        return "transposed"
    success = detect_opening_success(board, plan, move_history, primary_move)
    progress = opening_progress_details_for(board, plan, move_history, success)
    line = plan.get("mainLineUci", [])
    minimum_ply = min(10, max(4, len(line)))
    enough_plan_moves = int(progress["planMovesPlayed"]) >= int(progress["planMovesTarget"])
    if int(progress["percent"]) >= 82 and enough_plan_moves and success["completed"] >= 3 and len(move_history) >= minimum_ply:
        return "opening_success"
    return "opening_in_progress"


def opening_state_for(
    *,
    board: chess.Board,
    plan: dict[str, Any] | None,
    status: str,
    phase: str,
    phase_status: str,
    move_history: list[str],
    plan_moves: list[str],
    primary_move: dict[str, Any] | None,
    deviation: dict[str, Any] | None,
) -> str:
    if not plan:
        return "recoverable"
    if phase_status == "opening_success" or status == "plan_completed":
        return "completed"
    if phase == "endgame":
        return "completed" if len(move_history) >= 8 else "recoverable"
    if status == "on_plan":
        return "on_track"

    progress = opening_progress_details_for(board, plan, move_history)
    playable_plan_move = bool(plan_moves)
    severe_warning = primary_move is not None and _is_severe_warning(primary_move)
    low_progress = int(progress["percent"]) < 45 and len(move_history) >= 8
    no_realistic_line = deviation is not None and not playable_plan_move and len(move_history) >= 6

    if severe_warning or no_realistic_line or (phase in {"transition", "middlegame"} and low_progress):
        return "abandoned"
    return "recoverable"


def strategic_plan_for(
    *,
    plan: dict[str, Any] | None,
    phase: str,
    opening_state: str,
    current_objective: str,
    what_changed: str,
    coach_context: dict[str, Any],
    primary_move: dict[str, Any] | None,
    expected_opponent_move: dict[str, Any] | None,
) -> dict[str, str]:
    plan_name = str(plan.get("nameFr")) if plan else "Plan general"
    if expected_opponent_move:
        return {
            "title": "Observer la reponse adverse",
            "goal": f"L'adversaire devrait surtout jouer {expected_opponent_move['beginnerLabel']}.",
            "reason": "C'est a l'autre camp de jouer, donc ton plan attend sa decision.",
            "nextObjective": "Regarde si sa reponse confirme le plan ou force une adaptation.",
        }
    if opening_state == "abandoned":
        goal = _first_coach_goal(coach_context) or "Stabiliser la position avant de chercher une attaque."
        return {
            "title": "Nouveau plan de jeu",
            "goal": goal,
            "reason": f"{plan_name} n'est plus realiste comme ligne d'ouverture sans prendre trop de risques.",
            "nextObjective": current_objective or "Ameliore ta pire piece et garde le roi en securite.",
        }
    if opening_state == "completed":
        goal = _first_coach_goal(coach_context) or (plan.get("middlegamePlan", ["Ameliorer les pieces."])[0] if plan else "Ameliorer les pieces.")
        return {
            "title": "Plan de milieu de partie",
            "goal": str(goal),
            "reason": "L'ouverture a rempli assez de criteres : le coach passe aux objectifs strategiques.",
            "nextObjective": current_objective,
        }
    if opening_state == "recoverable":
        return {
            "title": "Ouverture adaptee",
            "goal": current_objective,
            "reason": what_changed,
            "nextObjective": "Garde l'idee du plan, mais ne force pas une ligne qui n'existe plus.",
        }
    if phase == "endgame":
        return {
            "title": "Plan de finale",
            "goal": _first_coach_goal(coach_context) or "Activer le roi et convertir sans contre-jeu.",
            "reason": "Il reste peu de materiel : les objectifs changent.",
            "nextObjective": current_objective,
        }
    return {
        "title": plan_name,
        "goal": current_objective,
        "reason": what_changed,
        "nextObjective": current_objective,
    }


def plan_event_for(plan: dict[str, Any] | None, phase: str, opening_state: str, strategic_plan: dict[str, str]) -> dict[str, str] | None:
    plan_id = str(plan.get("id")) if plan else "general"
    if opening_state == "abandoned":
        return {
            "id": f"opening-abandoned-{plan_id}",
            "severity": "warning",
            "title": "Plan initial abandonne",
            "message": strategic_plan["reason"],
        }
    if opening_state == "completed":
        return {
            "id": f"opening-completed-{plan_id}",
            "severity": "success",
            "title": "Ouverture terminee",
            "message": "On passe maintenant au plan de milieu de partie.",
        }
    if phase == "endgame":
        return {
            "id": "phase-endgame",
            "severity": "info",
            "title": "Finale",
            "message": "Le plan devient conversion, securite du roi et pions passes.",
        }
    return None


def phase_reason_for(
    phase: str,
    opening_state: str,
    plan: dict[str, Any] | None,
    progress: dict[str, Any],
    coach_context: dict[str, Any],
) -> str:
    if opening_state == "abandoned":
        return "La ligne d'ouverture choisie n'est plus realiste dans cette position."
    if opening_state == "completed":
        return "Les criteres d'ouverture sont assez remplis pour passer au milieu de partie."
    if phase == "endgame":
        return "Le materiel restant indique une finale."
    if phase in {"transition", "middlegame"}:
        return str(coach_context.get("mainGoal") or "La position demande un plan strategique plutot qu'une ligne d'ouverture.")
    if plan:
        return str(progress.get("impact") or "Le coach verifie si l'ouverture peut encore etre construite.")
    return "Le coach applique les principes d'ouverture generaux."


def _first_coach_goal(coach_context: dict[str, Any]) -> str | None:
    for key in ("currentPriorities", "conversionPlan"):
        values = coach_context.get(key)
        if isinstance(values, list) and values:
            return str(values[0])
    candidate_plans = coach_context.get("candidatePlans")
    if isinstance(candidate_plans, list) and candidate_plans:
        first = candidate_plans[0]
        if isinstance(first, dict):
            return str(first.get("name") or first.get("why") or "")
    return None


def plan_progress_for(board: chess.Board, plan: dict[str, Any] | None, move_history: list[str], phase_status: str) -> dict[str, Any]:
    if not plan:
        return {"percent": 0, "completed": 0, "total": 0, "criteria": []}
    details = opening_progress_details_for(board, plan, move_history)
    if phase_status == "opening_success":
        details["percent"] = 100
        details["impact"] = "Ouverture terminee : tu peux maintenant jouer les objectifs de milieu de partie."
    return details


def opening_progress_details_for(
    board: chess.Board,
    plan: dict[str, Any],
    move_history: list[str],
    success: dict[str, Any] | None = None,
) -> dict[str, Any]:
    success = success or detect_opening_success(board, plan, move_history, None)
    plan_color = color_for_plan(plan)
    line = plan.get("mainLineUci", [])
    plan_line_moves = [
        move
        for index, move in enumerate(line)
        if plan_color is None or color_for_ply_index(index) == plan_color
    ]
    played_plan_moves = [
        move
        for index, move in enumerate(move_history)
        if plan_color is None or color_for_ply_index(index) == plan_color
    ]
    exact_plan_moves = [
        move
        for index, move in enumerate(move_history)
        if index < len(line) and move == line[index] and (plan_color is None or color_for_ply_index(index) == plan_color)
    ]
    plan_target = max(2, min(4, len(plan_line_moves) or 3))
    exact_total = max(1, len(plan_line_moves))
    exact_ratio = min(1.0, len(exact_plan_moves) / exact_total)
    plan_move_ratio = min(1.0, len(played_plan_moves) / plan_target)
    criteria_ratio = success["completed"] / max(1, success["total"])
    raw_percent = round(exact_ratio * 42 + plan_move_ratio * 34 + criteria_ratio * 24)
    percent = 0 if not move_history else min(96, max(8, raw_percent))
    return {
        "percent": percent,
        "completed": success["completed"],
        "total": success["total"],
        "criteria": success["criteria"],
        "linePly": len(exact_plan_moves),
        "lineTotal": exact_total,
        "tempoPly": len(played_plan_moves),
        "tempoTotal": plan_target,
        "planMovesPlayed": len(played_plan_moves),
        "planMovesTarget": plan_target,
        "exactPlanMoves": len(exact_plan_moves),
        "exactPlanTotal": exact_total,
        "impact": progress_impact_for(plan, move_history, plan_color, percent),
    }


def detect_opening_success(
    board: chess.Board,
    plan: dict[str, Any],
    move_history: list[str],
    primary_move: dict[str, Any] | None,
) -> dict[str, Any]:
    line = plan.get("mainLineUci", [])
    line_or_branch = len(move_history) >= len(line)
    criteria = [
        {"label": "Ligne principale ou branche cohérente atteinte.", "ok": line_or_branch},
        {"label": "Sécurité du roi traitée ou devenue l'objectif prioritaire.", "ok": king_safety_handled(board, plan)},
        {"label": "Pièces mineures principales développées.", "ok": minor_pieces_developed(board, plan)},
        {"label": "Centre contesté, clarifié ou stabilisé.", "ok": center_contested(board)},
        {"label": "Pas d'avertissement tactique grave.", "ok": primary_move is None or not _is_severe_warning(primary_move)},
    ]
    completed = sum(1 for item in criteria if item["ok"])
    return {"completed": completed, "total": len(criteria), "criteria": criteria}


def current_objective_for(plan: dict[str, Any] | None, phase: str, primary_move: dict[str, Any] | None) -> str:
    if primary_move:
        return str(primary_move["purpose"])
    if phase == "middlegame" and plan and plan.get("middlegamePlan"):
        return str(plan["middlegamePlan"][0])
    if phase == "endgame" and plan and plan.get("endgamePlan"):
        return str(plan["endgamePlan"][0])
    return fallback_goals(phase)[0]


def last_event_for(move_history: list[str]) -> str:
    if not move_history:
        return "La partie commence. Le premier coup sert a installer ton plan."
    board = chess.Board()
    for move_uci in move_history[:-1]:
        try:
            board.push_uci(move_uci)
        except ValueError:
            return "Le dernier coup est connu, mais son ordre exact n'a pas pu etre reconstruit."
    last_move = move_history[-1]
    side = "Les blancs" if board.turn == chess.WHITE else "Les noirs"
    try:
        notation = beginner_notation_for_uci(board.fen(), last_move)
    except Exception:
        return f"{side} viennent de jouer {last_move}."
    return f"{side} viennent de jouer {notation.beginner_label}."


def what_changed_for(
    plan: dict[str, Any] | None,
    status: str,
    phase_status: str,
    deviation: dict[str, Any] | None,
    primary_move: dict[str, Any] | None,
) -> str:
    plan_name = plan.get("nameFr") if plan else "le plan general"
    if phase_status == "opening_success":
        return "L'ouverture a rempli assez de criteres : on peut passer au plan de milieu de partie."
    if deviation:
        if deviation.get("expected"):
            return f"L'adversaire a choisi une autre reponse. On garde {plan_name}, mais le prochain coup change pour rester logique."
        return f"La ligne exacte de {plan_name} est terminee. On garde ses idees principales et on choisit un objectif concret."
    if status == "on_plan":
        return f"Rien ne force a changer de direction : {plan_name} reste coherent."
    if primary_move and primary_move.get("warning"):
        return "Le coup attendu demande de la prudence : une menace concrete oblige a adapter le plan."
    return "La position est reliee au plan choisi et les coups proposes restent prudents."


def pedagogical_summary_for(coach_message: str, what_changed: str, next_objective: str) -> str:
    return f"{coach_message} {what_changed} Prochain objectif : {next_objective}"


def coach_message_for(plan: dict[str, Any] | None, status: str, phase_status: str, locked_plan: bool) -> str:
    plan_name = plan.get("nameFr") if plan else "le plan général"
    if phase_status == "opening_success":
        return f"Ouverture réussie : {plan_name} a donné une structure jouable. On passe maintenant au plan de milieu de partie."
    if status == "opponent_deviated":
        return f"L'adversaire a dévié, mais on garde {plan_name}. Le prochain coup est adapté pour rester cohérent avec ce plan."
    if status == "transposed":
        return f"La position ressemble à une autre ouverture, mais ton plan reste verrouillé sur {plan_name}."
    if locked_plan:
        return f"Tu suis {plan_name}. Le coach cherche d'abord le coup qui construit cette ouverture."
    return explain_opening_status({"planName": plan_name, "status": status})


def king_safety_handled(board: chess.Board, plan: dict[str, Any]) -> bool:
    color = chess.WHITE if plan.get("side") == "white" else chess.BLACK
    king_square = board.king(color)
    if king_square is None:
        return False
    king_file = chess.square_file(king_square)
    return king_file in {1, 2, 6, 7} or board.fullmove_number >= 6


def minor_pieces_developed(board: chess.Board, plan: dict[str, Any]) -> bool:
    color = chess.WHITE if plan.get("side") == "white" else chess.BLACK
    home_squares = [chess.B1, chess.G1, chess.C1, chess.F1] if color == chess.WHITE else [chess.B8, chess.G8, chess.C8, chess.F8]
    remaining = 0
    for square in home_squares:
        piece = board.piece_at(square)
        if piece and piece.color == color and piece.piece_type in {chess.KNIGHT, chess.BISHOP}:
            remaining += 1
    return remaining <= 2


def center_contested(board: chess.Board) -> bool:
    center = [chess.D4, chess.E4, chess.D5, chess.E5]
    occupied = any(board.piece_at(square) for square in center)
    attacked = any(board.attackers(chess.WHITE, square) or board.attackers(chess.BLACK, square) for square in center)
    return occupied or attacked


def _is_legal_uci(board: chess.Board, move_uci: str) -> bool:
    try:
        return chess.Move.from_uci(move_uci) in board.legal_moves
    except ValueError:
        return False


def _is_prefix(prefix: list[str], line: list[str]) -> bool:
    return all(index < len(line) and move == line[index] for index, move in enumerate(prefix))


def _is_severe_warning(item: dict[str, Any]) -> bool:
    return bool(item.get("warning")) and int(item.get("engineScore", 0)) < 45
