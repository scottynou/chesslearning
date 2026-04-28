from __future__ import annotations

import os
from typing import Any

import chess

from ..ai_reranker import rerank_recommendations
from ..beginner_notation import beginner_notation_for_uci
from ..elo_ranker import rank_candidates
from ..evaluation_label import evaluation_label
from ..stockfish_engine import StockfishEngine
from .endgame_coach import analyze_endgame
from .middlegame_coach import analyze_middlegame
from .move_merger import merge_plan_and_engine_moves
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
    max_moves: int = 10,
    engine_depth: int = 10,
    user_side: str | None = None,
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

    plan_can_drive_opening = phase == "opening" and status == "on_plan" and bool(plan_moves)
    if game_over or plan_can_drive_opening:
        engine_lines = []
        engine_candidates = []
    else:
        safety_window = min(10, max(4, int(level_settings["technical_limit"]) * 2))
        multipv = min(24, safety_window * 2)
        recommend_ms = _int_env("STOCKFISH_RECOMMEND_MS", 700)
        critical_ms = _int_env("STOCKFISH_CRITICAL_MS", 1200)
        engine_lines = StockfishEngine().analyze(fen, multipv=multipv, depth=engine_depth, movetime_ms=recommend_ms)
        engine_candidates = rank_candidates(fen, engine_lines, elo=elo, max_moves=safety_window)
        if (
            critical_ms > recommend_ms
            and engine_candidates
            and (mate_danger_from_side_to_move(engine_candidates) == "critical" or score_from_side_to_move(engine_candidates) <= -260)
        ):
            engine_lines = StockfishEngine().analyze(fen, multipv=multipv, depth=engine_depth, movetime_ms=critical_ms)
            engine_candidates = rank_candidates(fen, engine_lines, elo=elo, max_moves=safety_window)
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
    accuracy_profile = accuracy_profile_for(
        board=board,
        phase_display=phase_display,
        phase_status=phase_status,
        opening_state=opening_state,
        engine_candidates=engine_candidates,
        move_history=move_history,
        player_turn=player_turn,
    )
    if player_turn and visible_merged and should_shape_for_human_accuracy(phase_display, phase_status, opening_state):
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
        visible_recommendations, ai_rerank_status = rerank_recommendations(
            fen=fen,
            selected_plan=active_plan,
            phase=phase,
            opening_state=opening_state,
            move_history=move_history,
            recommendations=visible_recommendations,
        )
        if should_shape_for_human_accuracy(phase_display, phase_status, opening_state):
            visible_recommendations = shape_recommendations_for_accuracy(visible_recommendations, accuracy_profile)
        visible_recommendations = decorate_recommendations(
            visible_recommendations,
            str(phase_display["recommendationStyle"]),
        )
    primary_move = visible_recommendations[0] if visible_recommendations else None
    adapted_alternatives = visible_recommendations[1:]
    blocked_expected_move = blocked_expected_move_for(primary_move, deviation)
    adaptive_signal = adaptive_signal_for(
        primary_move=primary_move,
        phase_status=phase_status,
        blocked_expected_move=blocked_expected_move,
        opening_state=opening_state,
        player_turn=player_turn,
        engine_candidates=engine_candidates,
        draw_pressure=accuracy_profile.get("drawPressure"),
    )
    current_objective = current_objective_for(active_plan, phase, primary_move)
    progress = plan_progress_for(board, active_plan, move_history, phase_status)
    opening_brief = opening_brief_for(active_plan)
    technical_moves = [candidate.model_dump(by_alias=True) for candidate in engine_candidates[: int(level_settings["technical_limit"])]]
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
        "aiRerankStatus": ai_rerank_status,
        "adaptiveSignal": adaptive_signal,
        "technicalDetails": {
            "engineDepth": engine_depth,
            "maxMoves": max_moves,
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
            "subtitle": "Convertis sans donner de contre-jeu.",
            "recommendationStyle": "conversion",
            "maxVisibleMoves": 2,
        }
    if display_phase == "middlegame":
        return {
            "key": "middlegame",
            "label": "Milieu de partie",
            "subtitle": "Choisis un plan humain : securite, activite, cible.",
            "recommendationStyle": "ranked",
            "maxVisibleMoves": 3,
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
    pool = [primary_move]
    for item in merged:
        if item["moveUci"] != primary_move["moveUci"] and not _is_severe_warning(item):
            pool.append(item)
    limit = int(phase_display["maxVisibleMoves"])
    return decorate_recommendations(pool[:limit], str(phase_display["recommendationStyle"]))


def decorate_recommendations(items: list[dict[str, Any]], style: str) -> list[dict[str, Any]]:
    labels = {
        "single": ["Coup du plan"],
        "ranked": ["Meilleur", "Alternative saine", "Option pratique"],
        "conversion": ["Conversion", "Securite"],
    }.get(style, ["Meilleur", "Alternative saine", "Option pratique"])
    colors = ["rgba(224,185,118,0.78)", "rgba(125,183,154,0.76)", "rgba(126,166,224,0.74)"]
    decorated = []
    for index, item in enumerate(items):
        copy = dict(item)
        copy["displayRank"] = index + 1
        copy["displayRole"] = labels[min(index, len(labels) - 1)]
        copy["arrowColor"] = colors[min(index, len(colors) - 1)]
        decorated.append(copy)
    return decorated


def should_shape_for_human_accuracy(phase_display: dict[str, Any], phase_status: str, opening_state: str) -> bool:
    if phase_display["key"] != "opening":
        return True
    return phase_status in {"adapted", "fallback"} or opening_state in {"recoverable", "abandoned"}


def accuracy_profile_for(
    *,
    board: chess.Board,
    phase_display: dict[str, Any],
    phase_status: str,
    opening_state: str,
    engine_candidates: list[Any],
    move_history: list[str],
    player_turn: bool,
) -> dict[str, Any]:
    draw_pressure = draw_pressure_for(
        board=board,
        phase_display=phase_display,
        move_history=move_history,
        engine_candidates=engine_candidates,
    )
    if not player_turn:
        return {
            "mode": "idle",
            "target": 84,
            "min": 78,
            "max": 88,
            "reason": "Hors tour joueur.",
            "drawPressure": draw_pressure,
        }

    position_score = score_from_side_to_move(engine_candidates)
    mating_danger = mate_danger_from_side_to_move(engine_candidates)
    phase_key = str(phase_display.get("key", "opening"))

    if mating_danger == "critical" or position_score <= -260:
        return {
            "mode": "survival",
            "target": 97,
            "min": 92,
            "max": 100,
            "reason": "Position critique : on accepte des coups tres proches du moteur pour ne pas perdre.",
            "drawPressure": draw_pressure,
        }
    if phase_status in {"adapted", "fallback"} or opening_state in {"recoverable", "abandoned"} or position_score <= -90:
        return {
            "mode": "pressure",
            "target": 90,
            "min": 84,
            "max": 96,
            "reason": "Sous pression : on monte la qualite sans devenir systematiquement machine.",
            "drawPressure": draw_pressure,
        }
    if draw_pressure["level"] == "critical":
        return {
            "mode": "draw_break",
            "target": 94,
            "min": 88,
            "max": 99,
            "reason": "La position devient trop nulle : on cherche des coups plus precis qui gardent des chances de gain.",
            "drawPressure": draw_pressure,
        }
    if draw_pressure["level"] == "warning":
        return {
            "mode": "draw_break",
            "target": 91,
            "min": 84,
            "max": 97,
            "reason": "Risque de simplification vers nulle : on augmente legerement la precision.",
            "drawPressure": draw_pressure,
        }
    if phase_key == "endgame":
        return {
            "mode": "conversion",
            "target": 88,
            "min": 82,
            "max": 94,
            "reason": "Finale : les coups doivent convertir proprement.",
            "drawPressure": draw_pressure,
        }
    if position_score >= 220:
        return {
            "mode": "comfortable",
            "target": 81,
            "min": 76,
            "max": 86,
            "reason": "Position confortable : on evite les coups inutilement parfaits.",
            "drawPressure": draw_pressure,
        }
    return {
        "mode": "human",
        "target": 84,
        "min": 78,
        "max": 89,
        "reason": "Zone humaine forte : proche du moteur, mais pas toujours top engine.",
        "drawPressure": draw_pressure,
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
    low_spread = candidate_score_spread(engine_candidates[:5]) <= 24

    base = {
        "level": "none",
        "reason": "Pas de signal de nulle.",
        "scoreCp": score,
        "pieceCount": piece_count,
        "pawns": pawns,
        "queens": queens,
    }

    if board.is_insufficient_material():
        return {**base, "level": "critical", "reason": "Materiel insuffisant : la partie tend deja vers nulle."}
    if board.halfmove_clock >= 86:
        return {**base, "level": "critical", "reason": "Regle des 50 coups proche : il faut creer une rupture utile."}
    if phase_key == "endgame" and abs_score <= 60 and (queens == 0 or pawns <= 6):
        return {**base, "level": "critical", "reason": "Finale tres egale avec peu de materiel."}
    if phase_key == "endgame" and abs_score <= 105:
        return {**base, "level": "warning", "reason": "Finale encore jouable mais trop proche de l'egalite."}
    if len(move_history) >= 22 and queens == 0 and major_pieces <= 4 and abs_score <= 70:
        return {**base, "level": "warning", "reason": "Les dames sont sorties et l'evaluation reste plate."}
    if len(move_history) >= 26 and abs_score <= 45 and low_spread:
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

    mode = str(profile.get("mode", "human"))
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
    viable = [
        item
        for item in candidates
        if int(item.get("engineScore") or 0) >= minimum
        or (int(item.get("planFitScore") or 0) >= 90 and int(item.get("engineScore") or 0) >= minimum - 6)
    ]
    if not viable:
        viable = sorted(candidates, key=lambda item: -int(item.get("engineScore") or 0))[: max(1, min(3, len(candidates)))]

    ordered = sorted(viable, key=lambda item: human_accuracy_sort_score(item, profile), reverse=True)
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


def human_accuracy_sort_score(item: dict[str, Any], profile: dict[str, Any]) -> float:
    engine_score = int(item.get("engineScore") or 0)
    plan_fit = int(item.get("planFitScore") or 0)
    simplicity = int(item.get("beginnerSimplicityScore") or 0)
    risk = int(item.get("tacticalRisk") or 0)
    final_score = int(item.get("finalCoachScore") or 0)
    target = int(profile.get("target", 84))
    minimum = int(profile.get("min", 78))
    maximum = int(profile.get("max", 89))
    mode = str(profile.get("mode", "human"))

    if mode == "draw_break":
        over_penalty = 0.25
        under_penalty = 3.6
        distance_penalty = 1.05
    elif mode == "pressure":
        over_penalty = 0.45
        under_penalty = 3.4
        distance_penalty = 1.35
    elif mode == "conversion":
        over_penalty = 0.75
        under_penalty = 3.1
        distance_penalty = 1.45
    elif mode == "comfortable":
        over_penalty = 2.1
        under_penalty = 2.7
        distance_penalty = 1.7
    else:
        over_penalty = 1.65
        under_penalty = 3.0
        distance_penalty = 1.55

    in_band_bonus = 22 if minimum <= engine_score <= maximum else 0
    plan_bonus = 9 if item.get("source") in {"plan", "plan_and_engine"} else 0
    return (
        in_band_bonus
        + plan_bonus
        + final_score * 0.24
        + plan_fit * 0.23
        + simplicity * 0.15
        + engine_score * 0.14
        + draw_avoidance_bonus(item, profile)
        - risk * 0.42
        - abs(engine_score - target) * distance_penalty
        - max(0, minimum - engine_score) * under_penalty
        - max(0, engine_score - maximum) * over_penalty
    )


def draw_avoidance_bonus(item: dict[str, Any], profile: dict[str, Any]) -> float:
    if str(profile.get("mode")) != "draw_break":
        return 0.0
    candidate_eval = candidate_eval_cp(item)
    engine_rank = item.get("engineRank") or 8
    tactical_risk = int(item.get("tacticalRisk") or 0)
    positive_eval_bonus = max(-40, min(220, candidate_eval)) * 0.10
    initiative_bonus = max(0, 8 - int(engine_rank)) * 1.2
    risk_penalty = max(0, tactical_risk - 26) * 0.45
    return positive_eval_bonus + initiative_bonus - risk_penalty


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


def annotate_accuracy(item: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    engine_score = int(item.get("engineScore") or 0)
    target = int(profile.get("target", 84))
    item["humanAccuracyEstimate"] = max(0, min(99, round(engine_score * 0.92 + target * 0.08)))
    item["accuracyBand"] = str(profile.get("mode", "human"))
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

    engine_score = int(primary_move.get("engineScore") or 100)
    tactical_risk = int(primary_move.get("tacticalRisk") or 0)
    warning = bool(primary_move.get("warning") or blocked_expected_move)
    adapted = phase_status in {"adapted", "fallback"} or opening_state in {"recoverable", "abandoned"}
    position_score = score_from_side_to_move(engine_candidates)
    mating_danger = mate_danger_from_side_to_move(engine_candidates)
    draw_level = str((draw_pressure or {}).get("level", "none"))

    if warning or mating_danger == "critical" or position_score <= -260 or engine_score <= 45 or tactical_risk >= 45:
        return {
            "pressure": "critical",
            "suggestedBoostDelta": 100,
            "reason": "La position est sous forte pression : le coach monte d'un cran pour chercher des coups plus precis.",
        }
    if draw_level == "critical":
        return {
            "pressure": "drawish",
            "suggestedBoostDelta": 100,
            "reason": "La partie risque de s'aplatir vers nulle : le coach monte en precision pour garder des chances de gain.",
        }
    if adapted or mating_danger == "warning" or position_score <= -90 or engine_score <= 65 or tactical_risk >= 28:
        return {
            "pressure": "worse",
            "suggestedBoostDelta": 50,
            "reason": "L'adversaire met assez de pression pour augmenter legerement le niveau cache.",
        }
    if draw_level == "warning":
        return {
            "pressure": "drawish",
            "suggestedBoostDelta": 50,
            "reason": "La position devient trop egale : le coach augmente legerement le niveau cache.",
        }
    if position_score >= 160 and engine_score >= 74 and tactical_risk <= 18 and not warning:
        return {
            "pressure": "stable",
            "suggestedBoostDelta": -50,
            "reason": "La position redevient confortable : le coach redescend progressivement.",
        }
    return {
        "pressure": "stable",
        "suggestedBoostDelta": 0,
        "reason": "Pas de changement utile du niveau cache.",
    }


def score_from_side_to_move(engine_candidates: list[Any]) -> int:
    if not engine_candidates:
        return 0
    candidate = engine_candidates[0]
    eval_cp = getattr(candidate, "eval_cp", None)
    if eval_cp is None:
        return 0
    return int(eval_cp)


def mate_danger_from_side_to_move(engine_candidates: list[Any]) -> str:
    if not engine_candidates:
        return "none"
    mate_in = getattr(engine_candidates[0], "mate_in", None)
    if mate_in is None:
        return "none"
    if mate_in < 0:
        return "critical"
    return "winning"


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
