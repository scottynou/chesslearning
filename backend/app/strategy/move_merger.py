from __future__ import annotations

import chess

from ..beginner_notation import beginner_notation_for_uci
from ..elo_ranker import compute_simplicity_score
from ..evaluation_label import evaluation_label
from ..schemas import CandidateMove
from ..stockfish_engine import EngineLine


def merge_plan_and_engine_moves(
    *,
    fen: str,
    plan_moves: list[str],
    engine_candidates: list[CandidateMove],
    engine_lines: list[EngineLine],
    plan_name: str | None,
    elo: int,
    current_step_index: int,
) -> list[dict[str, object]]:
    board = chess.Board(fen)
    engine_by_uci = {candidate.move_uci: candidate for candidate in engine_candidates}
    engine_line_by_uci = {line.move_uci: line for line in engine_lines}
    merged_order: list[str] = []

    for move in plan_moves:
        if move not in merged_order:
            merged_order.append(move)
    for candidate in engine_candidates:
        if candidate.move_uci not in merged_order:
            merged_order.append(candidate.move_uci)

    recommendations = []
    for move_uci in merged_order:
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            continue
        if move not in board.legal_moves:
            continue

        engine_candidate = engine_by_uci.get(move_uci)
        engine_line = engine_line_by_uci.get(move_uci)
        plan_rank = plan_moves.index(move_uci) + 1 if move_uci in plan_moves else None
        is_plan_move = plan_rank is not None
        plan_fit = plan_fit_score(plan_rank, plan_name)
        engine_score = engine_candidate.engine_score if engine_candidate else (74 if is_plan_move else 45)
        simplicity = engine_candidate.simplicity_score if engine_candidate else (76 if is_plan_move and engine_line is None else _simplicity_from_line(board, move, engine_line))
        tactical_risk = engine_candidate.risk_penalty if engine_candidate else (12 if is_plan_move else 25)
        final_score = final_coach_score(engine_score, plan_fit, simplicity, tactical_risk, elo)
        source = source_label(plan_rank, engine_candidate)
        notation = beginner_notation_for_uci(fen, move_uci, engine_candidate.move_san if engine_candidate else None)
        warning = safety_warning(engine_score, plan_rank)
        purpose = purpose_for_move(notation.piece_name, notation.to_square)
        connection = plan_connection(plan_name, current_step_index, plan_rank)
        complexity = move_complexity(simplicity, tactical_risk, source)

        recommendations.append(
            {
                "moveUci": move_uci,
                "moveSan": notation.san,
                "beginnerLabel": notation.beginner_label,
                "source": source,
                "engineRank": engine_candidate.stockfish_rank if engine_candidate else None,
                "planRank": plan_rank,
                "planFitScore": plan_fit,
                "engineScore": engine_score,
                "beginnerSimplicityScore": simplicity,
                "tacticalRisk": tactical_risk,
                "finalCoachScore": final_score,
                "evalLabel": evaluation_label(engine_candidate.eval_cp, engine_candidate.mate_in) if engine_candidate else ("Coup du plan" if is_plan_move else "A verifier avec le moteur"),
                "purpose": purpose,
                "planConnection": connection,
                "pedagogicalExplanation": pedagogical_explanation(
                    beginner_label=notation.beginner_label,
                    purpose=purpose,
                    connection=connection,
                    warning=warning,
                    complexity=complexity,
                ),
                "moveComplexity": complexity,
                "warning": warning,
                "candidate": engine_candidate.model_dump(by_alias=True) if engine_candidate else None,
            }
        )

    return sorted(recommendations, key=lambda item: (-int(item["finalCoachScore"]), item["planRank"] or 99))[:10]


def final_coach_score(engine_score: int, plan_fit: int, simplicity: int, tactical_risk: int, elo: int) -> int:
    if elo <= 1000:
        weights = (0.35, 0.40, 0.22, 0.18)
    elif elo <= 1800:
        weights = (0.58, 0.27, 0.10, 0.16)
    elif elo < 2800:
        weights = (0.72, 0.18, 0.07, 0.12)
    else:
        weights = (0.90, 0.06, 0.03, 0.04)
    score = weights[0] * engine_score + weights[1] * plan_fit + weights[2] * simplicity - weights[3] * tactical_risk
    return max(0, min(100, round(score)))


def plan_fit_score(plan_rank: int | None, plan_name: str | None) -> int:
    if not plan_name or plan_rank is None:
        return 35
    return max(55, 100 - (plan_rank - 1) * 10)


def safety_warning(engine_score: int, plan_rank: int | None) -> str | None:
    if plan_rank is not None and engine_score < 45:
        return "Ce coup du plan est trop dangereux dans cette position. Il faut d'abord regler la menace."
    if plan_rank is not None and engine_score < 65:
        return "Ce coup reste possible, mais regarde d'abord si une piece est attaquee."
    return None


def source_label(plan_rank: int | None, engine_candidate: CandidateMove | None) -> str:
    if plan_rank is not None and engine_candidate is not None:
        return "plan_and_engine"
    if plan_rank is not None:
        return "plan"
    if engine_candidate is not None:
        return "engine"
    return "fallback_principle"


def purpose_for_move(piece_name: str, to_square: str) -> str:
    if piece_name == "Cavalier":
        return f"Le cavalier arrive en {to_square}, une case plus active d'ou il aide a controler le centre."
    if piece_name == "Pion" and to_square in {"c5", "d5", "e5", "c4", "d4", "e4"}:
        return f"Le pion va en {to_square} pour prendre de l'espace au centre et ouvrir le jeu des pieces."
    if piece_name == "Fou":
        return f"Le fou va en {to_square}, devient actif et aide a preparer la securite du roi."
    return f"{piece_name} va en {to_square} pour ameliorer sa place sans casser la structure."


def move_complexity(simplicity: int, tactical_risk: int, source: str) -> str:
    if tactical_risk >= 35 or simplicity < 45:
        return "complexe"
    if tactical_risk >= 18 or simplicity < 68 or source == "engine":
        return "moyen"
    return "simple"


def pedagogical_explanation(
    *,
    beginner_label: str,
    purpose: str,
    connection: str,
    warning: str | None,
    complexity: str,
) -> str:
    base = f"Joue {beginner_label}. {purpose} {connection}"
    if warning:
        return f"{base} Attention : {warning}"
    if complexity == "simple":
        return f"{base} C'est un coup facile a jouer : il donne une position claire et prepare la suite de l'ouverture."
    if complexity == "moyen":
        return f"{base} C'est un coup logique, mais il demande de regarder ce que l'autre camp attaque ensuite."
    return f"{base} C'est un coup plus exigeant : choisis-le seulement si tu comprends la reponse attendue."


def plan_connection(plan_name: str | None, current_step_index: int, plan_rank: int | None) -> str:
    if not plan_name or plan_rank is None:
        return "Il suit un principe simple : centre, pieces actives ou roi en securite."
    return f"C'est l'etape {current_step_index + plan_rank} du plan {plan_name}."


def _simplicity_from_line(board: chess.Board, move: chess.Move, engine_line: EngineLine | None) -> int:
    if engine_line is None:
        return 55
    return compute_simplicity_score(board, move, engine_line)
