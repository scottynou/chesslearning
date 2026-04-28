from __future__ import annotations

from typing import Any

import chess

from ..beginner_notation import beginner_notation_for_uci
from ..elo_ranker import rank_candidates
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
    game_over = board.is_game_over()
    opponent_turn = not game_over and active_plan is not None and plan_color is not None and board.turn != plan_color
    player_turn = not game_over and not opponent_turn
    level_settings = skill_level_settings(skill_level, elo, max_moves)

    plan_can_drive_opening = phase == "opening" and status == "on_plan" and bool(plan_moves)
    if game_over or plan_can_drive_opening:
        engine_lines = []
        engine_candidates = []
    else:
        safety_window = min(10, max(4, int(level_settings["technical_limit"]) * 2))
        multipv = min(24, safety_window * 2)
        engine_lines = StockfishEngine().analyze(fen, multipv=multipv, depth=engine_depth)
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
    expected_opponent_move = expected_opponent_move_for(choose_primary_move(plan_items, merged)) if opponent_turn else None
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
    if phase_status == "opening_success":
        phase = "middlegame"
        status = "plan_completed"
        visible_plan_items = []
        strategic_pool = [item for item in visible_merged if item["source"] == "engine"] or visible_merged
        primary_move = choose_primary_move([], strategic_pool)

    phase_display = phase_display_for(phase, phase_status)
    visible_recommendations = visible_recommendations_for(
        phase_display=phase_display,
        primary_move=primary_move,
        merged=visible_merged,
    )
    primary_move = visible_recommendations[0] if visible_recommendations else None
    adapted_alternatives = visible_recommendations[1:]
    blocked_expected_move = blocked_expected_move_for(primary_move, deviation)
    current_objective = current_objective_for(active_plan, phase, primary_move)
    progress = plan_progress_for(board, active_plan, move_history, phase_status)
    opening_brief = opening_brief_for(active_plan)
    technical_moves = [candidate.model_dump(by_alias=True) for candidate in engine_candidates[: int(level_settings["technical_limit"])]]
    coach_message = coach_message_for(active_plan, status, phase_status, locked_plan)
    last_event = last_event_for(move_history)
    what_changed = what_changed_for(active_plan, status, phase_status, deviation, primary_move)
    next_objective = current_objective
    pedagogical_summary = pedagogical_summary_for(coach_message, what_changed, next_objective)
    response_move_complexity = str(primary_move.get("moveComplexity", "simple")) if primary_move else "simple"

    plan_state = {
        "selectedPlanId": active_plan.get("id") if active_plan else None,
        "planName": active_plan.get("nameFr") if active_plan else None,
        "side": active_plan.get("side") if active_plan else ("white" if board.turn == chess.WHITE else "black"),
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
        "planSide": active_plan.get("side") if active_plan else None,
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
            "phaseCoach": phase_coach(fen, phase),
            "skillLevel": level_settings,
        },
        "selectedPlan": active_plan,
        "phase": phase,
        "phaseDisplay": phase_display,
        "phaseStatus": phase_status,
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


def expected_opponent_move_for(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    copy = dict(item)
    copy["displayRank"] = 1
    copy["displayRole"] = "Coup adverse attendu"
    copy["arrowColor"] = "rgba(239,118,118,0.78)"
    return copy


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
    success = detect_opening_success(board, plan, move_history, primary_move)
    progress = opening_progress_details_for(board, plan, move_history, success)
    line = plan.get("mainLineUci", [])
    minimum_ply = min(10, max(4, len(line)))
    enough_plan_moves = int(progress["planMovesPlayed"]) >= int(progress["planMovesTarget"])
    if int(progress["percent"]) >= 82 and enough_plan_moves and success["completed"] >= 3 and len(move_history) >= minimum_ply:
        return "opening_success"
    if status == "opponent_deviated":
        return "adapted"
    if status == "transposed":
        return "transposed"
    return "opening_in_progress"


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
