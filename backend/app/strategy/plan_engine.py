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
    level_settings = skill_level_settings(skill_level, elo, max_moves)

    safety_window = min(10, max(10, int(level_settings["technical_limit"]) * 2))
    multipv = min(30, safety_window * 3)
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
    primary_move = choose_primary_move(plan_items, merged)
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

    adapted_alternatives = adapted_alternatives_for(
        merged=merged,
        primary_move=primary_move,
        status=status,
        limit=int(level_settings["alternative_limit"]),
    )
    blocked_expected_move = blocked_expected_move_for(primary_move, deviation)
    current_objective = current_objective_for(active_plan, phase, primary_move)
    progress = plan_progress_for(board, active_plan, move_history, phase_status)
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
        "nextObjectives": next_objectives(active_plan, phase, merged),
        "knownOpponentDeviation": deviation,
        "recommendedPlanMoves": plan_moves,
        "fallbackPrinciples": fallback_goals(phase),
        "engineSafetyWarning": next((item["warning"] for item in merged if item.get("warning")), None),
        "statusExplanation": coach_message,
    }

    return {
        "planState": plan_state,
        "planMoves": plan_items,
        "engineMoves": technical_moves,
        "mergedRecommendations": merged,
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
        "phaseStatus": phase_status,
        "planProgress": progress,
        "currentObjective": current_objective,
        "lastEvent": last_event,
        "whatChanged": what_changed,
        "nextObjective": next_objective,
        "recommendedPlanMoves": plan_items,
        "primaryMove": primary_move,
        "adaptedAlternatives": adapted_alternatives,
        "blockedExpectedMove": blocked_expected_move,
        "coachMessage": coach_message,
        "pedagogicalSummary": pedagogical_summary,
        "moveComplexity": response_move_complexity,
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
        "mainGoal": "Suivre le plan choisi sans ignorer les menaces tactiques.",
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
    if detect_opening_success(board, plan, move_history, primary_move)["completed"] >= 3:
        return "opening_success"
    if status == "opponent_deviated":
        return "adapted"
    if status == "transposed":
        return "transposed"
    if status == "plan_completed":
        return "opening_success"
    return "opening_in_progress"


def plan_progress_for(board: chess.Board, plan: dict[str, Any] | None, move_history: list[str], phase_status: str) -> dict[str, Any]:
    if not plan:
        return {"percent": 0, "completed": 0, "total": 0, "criteria": []}
    success = detect_opening_success(board, plan, move_history, None)
    total_line = max(1, len(plan.get("mainLineUci", [])))
    line_percent = min(100, round((min(len(move_history), total_line) / total_line) * 100))
    criteria_percent = round((success["completed"] / max(1, success["total"])) * 100)
    percent = 100 if phase_status == "opening_success" else max(line_percent, criteria_percent)
    return {
        "percent": percent,
        "completed": success["completed"],
        "total": success["total"],
        "criteria": success["criteria"],
        "linePly": min(len(move_history), total_line),
        "lineTotal": total_line,
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
        return "La partie n'a pas encore commence. Choisis le premier objectif du plan."
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
            return f"L'adversaire n'a pas suivi la ligne attendue. On garde {plan_name}, mais le prochain coup doit s'adapter a cette position."
        return f"La ligne exacte de {plan_name} est terminee. On garde les idees du plan et on choisit un objectif concret."
    if status == "on_plan":
        return f"Rien ne force a changer de direction : {plan_name} reste coherent."
    if primary_move and primary_move.get("warning"):
        return "Le coup attendu demande de la prudence : Stockfish signale un risque tactique."
    return "Le coach relie maintenant la position au plan choisi et verifie les coups surs."


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
        return f"Tu suis {plan_name}. Le coach cherche le prochain coup du plan, puis vérifie avec Stockfish qu'il reste sain."
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
