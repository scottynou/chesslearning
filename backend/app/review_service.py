from __future__ import annotations

import os

import chess

from .ai_providers.gemini_provider import GeminiProvider
from .ai_providers.heuristic_provider import HeuristicProvider
from .ai_providers.ollama_provider import OllamaProvider
from .ai_providers.openai_provider import OpenAiProvider
from .beginner_notation import beginner_notation_for_uci
from .elo_ranker import _score_value, rank_candidates
from .evaluation_label import evaluation_label
from .pv_translator import simple_move_explanation
from .schemas import ReviewMoveRequest, ReviewMoveResponse
from .stockfish_engine import StockfishEngine
from .strategy.opening_coach import get_plan


QUALITY_LABELS = {
    "excellent": "Excellent",
    "good": "Bon coup",
    "playable": "Jouable",
    "inaccurate": "Imprecis",
    "mistake": "Erreur",
    "blunder": "Grosse erreur",
}

REVIEW_PROVIDERS = {
    "heuristic": HeuristicProvider,
    "openai": OpenAiProvider,
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
}


def review_move(request: ReviewMoveRequest, depth: int = 10) -> ReviewMoveResponse:
    board_before = chess.Board(request.fen_before)
    board_after = chess.Board(request.fen_after)
    played_move = chess.Move.from_uci(request.move_uci)
    played_san = board_before.san(played_move) if played_move in board_before.legal_moves else request.move_uci
    played_notation = beginner_notation_for_uci(request.fen_before, request.move_uci, played_san)

    engine = StockfishEngine()
    before_lines = engine.analyze(request.fen_before, multipv=10, depth=depth)
    before_candidates = rank_candidates(request.fen_before, before_lines, request.elo, max_moves=10)
    best_candidate = min(before_candidates, key=lambda candidate: candidate.stockfish_rank, default=None)

    played_candidate = next((candidate for candidate in before_candidates if candidate.move_uci == request.move_uci), None)
    best_score = _score_value(before_lines[0]) if before_lines else 0

    if played_candidate is not None:
        played_line = next((line for line in before_lines if line.move_uci == request.move_uci), None)
        played_score = _score_value(played_line) if played_line else best_score
        played_eval_cp = played_candidate.eval_cp
        played_mate = played_candidate.mate_in
    else:
        after_lines = engine.analyze(request.fen_after, multipv=1, depth=depth)
        after_score = _score_value(after_lines[0]) if after_lines else 0
        played_score = -after_score
        played_eval_cp = -after_lines[0].eval_cp if after_lines and after_lines[0].eval_cp is not None else None
        played_mate = -after_lines[0].mate_in if after_lines and after_lines[0].mate_in is not None else None

    loss = max(0, best_score - played_score)
    quality = classify_quality(loss)

    if best_candidate is not None:
        best_notation = beginner_notation_for_uci(request.fen_before, best_candidate.move_uci, best_candidate.move_san)
        best_label = best_notation.beginner_label
        best_uci = best_candidate.move_uci
        best_different = best_candidate.move_uci != request.move_uci
    else:
        best_label = played_notation.beginner_label
        best_uci = request.move_uci
        best_different = False

    what_it_does = simple_move_explanation(board_before, played_move)
    to_square = played_notation.to_square
    piece = played_notation.piece_name
    active_plan = get_plan(request.selected_plan_id)
    connection = _connection_to_plan(
        plan=active_plan,
        move_history=request.move_history_uci,
        move_uci=request.move_uci,
        best_label=best_label,
        best_uci=best_uci,
        quality=quality,
    )
    comparison = _comparison(best_label, best_different, quality)
    narrative_context = _review_context(
        request=request,
        active_plan=active_plan,
        move_label=played_notation.beginner_label,
        quality_label=QUALITY_LABELS[quality],
        played_eval_label=evaluation_label(played_eval_cp, played_mate),
        best_label=best_label,
        connection=connection,
        comparison=comparison,
        what_it_does=what_it_does,
    )
    coach_narrative, analysis_provider, analysis_kind = _coach_narrative(narrative_context)

    return ReviewMoveResponse(
        moveLabel=played_notation.beginner_label,
        coachNarrative=coach_narrative,
        analysisProvider=analysis_provider,
        analysisKind=analysis_kind,
        quality=quality,
        qualityLabel=QUALITY_LABELS[quality],
        playedMoveEvalLabel=evaluation_label(played_eval_cp, played_mate),
        bestMoveLabel=best_label,
        bestMoveWasDifferent=best_different,
        explanation={
            "probableIdea": f"L'idee probable est de placer le {piece} en {to_square} pour modifier le centre, le developpement ou la securite du roi.",
            "whatItDoes": what_it_does,
            "whatItAllows": _what_it_allows(piece, to_square, board_after),
            "whatToWatch": _what_to_watch(piece, to_square, quality),
            "comparisonWithBest": comparison,
        },
        connectionToPlan=connection,
        whatItAttacks=_attacked_squares(board_before, played_move),
        whatItDefends=[],
        whatItAllowsNext=_next_steps(piece, to_square),
        bestAlternative={
            "moveLabel": best_label,
            "whyBetterOrDifferent": comparison,
        },
        warning=_what_to_watch(piece, to_square, quality),
    )


def _review_context(
    *,
    request: ReviewMoveRequest,
    active_plan: dict | None,
    move_label: str,
    quality_label: str,
    played_eval_label: str,
    best_label: str,
    connection: str,
    comparison: str,
    what_it_does: str,
) -> dict:
    return {
        "fenBefore": request.fen_before,
        "fenAfter": request.fen_after,
        "moveHistoryUci": request.move_history_uci,
        "moveHistoryPgn": request.move_history_pgn,
        "phaseLabel": _phase_label(request.move_history_uci, request.fen_after),
        "plan": active_plan,
        "playedMove": {
            "uci": request.move_uci,
            "beginnerLabel": move_label,
        },
        "qualityLabel": quality_label,
        "playedMoveEvalLabel": played_eval_label,
        "bestAlternative": {
            "moveLabel": best_label,
        },
        "connectionToPlan": connection,
        "comparisonWithBest": comparison,
        "whatItDoes": what_it_does,
    }


def _coach_narrative(context: dict) -> tuple[str, str, str]:
    provider_name = os.getenv("AI_PROVIDER", "heuristic").lower()
    provider_cls = REVIEW_PROVIDERS.get(provider_name, HeuristicProvider)
    timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "18"))

    try:
        data = provider_cls().review_move(context, timeout_seconds=timeout)
        narrative = str(data.get("coachNarrative", "")).strip()
        if narrative:
            return narrative, provider_name if provider_name in REVIEW_PROVIDERS else "heuristic", "heuristic" if provider_name == "heuristic" else "ai"
    except Exception:
        pass

    fallback = HeuristicProvider().review_move(context, timeout_seconds=0)
    return str(fallback["coachNarrative"]), "heuristic", "heuristic"


def _phase_label(move_history: list[str], fen_after: str) -> str:
    if len(chess.Board(fen_after).piece_map()) <= 12:
        return "la finale"
    if len(move_history) <= 10:
        return "l'ouverture"
    return "le milieu de partie"


def classify_quality(loss_cp: int) -> str:
    if loss_cp <= 20:
        return "excellent"
    if loss_cp <= 50:
        return "good"
    if loss_cp <= 75:
        return "playable"
    if loss_cp <= 100:
        return "inaccurate"
    if loss_cp <= 200:
        return "mistake"
    return "blunder"


def _what_it_allows(piece: str, to_square: str, board_after: chess.Board) -> str:
    if piece == "Cavalier":
        return f"Depuis {to_square}, le Cavalier peut controler le centre, defendre une case utile ou preparer le roque."
    if piece == "Fou":
        return f"Depuis {to_square}, le Fou ouvre une diagonale et change les cases que ton plan doit surveiller."
    if piece == "Pion":
        return f"Le Pion en {to_square} change la structure. Il peut gagner de l'espace, soutenir le centre ou laisser une case derriere lui."
    if board_after.is_check():
        return "Ce coup cree aussi un echec, donc la reponse prioritaire devient la securite du roi."
    return f"La piece en {to_square} peut soutenir un plan plus large ou creer une nouvelle cible."


def _what_to_watch(piece: str, to_square: str, quality: str) -> str:
    if quality in {"mistake", "blunder"}:
        return "Ce coup semble moins optimise : cherche tout de suite le gain de temps, de centre ou de securite qu'il te donne."
    if piece == "Cavalier":
        return f"Surveille les cases centrales autour du Cavalier en {to_square} et garde ton developpement fluide."
    if piece == "Pion":
        return f"Apres ce Pion en {to_square}, regarde les cases qu'il ne defend plus et les ruptures de centre possibles."
    return f"Verifie que la piece en {to_square} ne cree pas une menace concrete contre ton plan."


def _comparison(best_label: str, best_different: bool, quality: str) -> str:
    if not best_different:
        return "Le coup joue correspond au meilleur repere de l'analyse."
    if quality in {"excellent", "good", "playable"}:
        return f"Il pouvait aussi choisir {best_label}. Le coup joue reste coherent, mais il peut changer l'ordre exact de ton plan."
    return f"Il aurait plutot du jouer {best_label}. Le coup joue est moins optimise parce qu'il peut perdre du temps, du controle ou de la securite."


def _connection_to_plan(
    plan: dict | None,
    move_history: list[str],
    move_uci: str,
    best_label: str,
    best_uci: str,
    quality: str,
) -> str:
    if not plan:
        return "Ce coup est compare aux principes de la position actuelle. Garde le centre, le developpement et la securite comme priorites."

    plan_name = str(plan.get("nameFr") or "ton plan")
    line = list(plan.get("mainLineUci") or [])
    ply_index = max(0, len(move_history) - 1)
    expected_uci = line[ply_index] if ply_index < len(line) else None

    if expected_uci == move_uci:
        return (
            f"L'adversaire a joue la reponse attendue par {plan_name}. Ton ouverture reste intacte : "
            "tu peux continuer le prochain repere du plan sans chercher une refutation."
        )

    if expected_uci:
        expected_label = _label_for_expected_move(expected_uci, move_history)
        if quality in {"excellent", "good", "playable"}:
            return (
                f"L'adversaire sort de la ligne de {plan_name}. La reponse attendue etait {expected_label}, "
                f"et l'autre bon repere etait {best_label}. Ce n'est pas forcement mauvais : ton plan reste vivant, "
                "mais le prochain coup doit etre choisi pour garder le centre et le developpement coherents."
            )
        return (
            f"L'adversaire ne joue pas la reponse attendue de {plan_name}. La ligne prevoyait {expected_label}; "
            f"le meilleur repere d'analyse etait {best_label}. Son coup semble moins precis, donc tu peux souvent "
            "gagner un tempo ou installer ton plan avec plus de confort."
        )

    if best_uci == move_uci:
        return (
            f"La ligne forcee de {plan_name} est deja depassee, mais le coup joue reste un bon repere. "
            "Continue avec les idees du plan plutot qu'avec une suite memorisee."
        )
    return (
        f"La ligne forcee de {plan_name} est depassee. Compare ce coup a {best_label}, puis adapte : "
        "garde les pieces actives, le roi en securite et une rupture centrale claire."
    )


def _label_for_expected_move(move_uci: str, move_history: list[str]) -> str:
    board = chess.Board()
    for played in move_history[:-1]:
        try:
            board.push_uci(played)
        except ValueError:
            break
    try:
        return beginner_notation_for_uci(board.fen(), move_uci).beginner_label
    except Exception:
        return move_uci


def _attacked_squares(board: chess.Board, move: chess.Move) -> list[str]:
    piece = board.piece_at(move.from_square)
    if not piece:
        return []
    temp = board.copy()
    if move in temp.legal_moves:
        temp.push(move)
    attacks = temp.attacks(move.to_square)
    important = []
    for square in attacks:
        name = chess.square_name(square)
        if name in {"e4", "d4", "e5", "d5", "c4", "c5", "f4", "f5"}:
            important.append(name)
    return important[:4]


def _next_steps(piece: str, to_square: str) -> list[str]:
    if piece == "Cavalier":
        return [
            f"Garder le Cavalier actif en {to_square}.",
            "Developper une autre piece.",
            "Preparer le roque ou contester le centre.",
        ]
    if piece == "Pion":
        return [
            f"Utiliser le Pion en {to_square} pour lire la structure.",
            "Sortir une piece mineure.",
            "Verifier que le roi reste en securite.",
        ]
    return [f"Verifier que la piece en {to_square} est bien defendue.", "Chercher le prochain objectif du plan."]
