from __future__ import annotations

import chess

from .beginner_notation import beginner_notation_for_uci
from .elo_ranker import _score_value, rank_candidates
from .evaluation_label import evaluation_label
from .pv_translator import simple_move_explanation
from .schemas import ReviewMoveRequest, ReviewMoveResponse
from .strategy.opening_coach import detect_current_opening
from .stockfish_engine import StockfishEngine


QUALITY_LABELS = {
    "excellent": "Excellent",
    "good": "Bon coup",
    "playable": "Jouable",
    "inaccurate": "Imprécis",
    "mistake": "Erreur",
    "blunder": "Grosse erreur",
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
        best_different = best_candidate.move_uci != request.move_uci
    else:
        best_label = played_notation.beginner_label
        best_different = False

    what_it_does = simple_move_explanation(board_before, played_move)
    to_square = played_notation.to_square
    piece = played_notation.piece_name

    connection = _connection_to_plan(request.move_history_pgn, request.move_uci)
    return ReviewMoveResponse(
        moveLabel=played_notation.beginner_label,
        quality=quality,
        qualityLabel=QUALITY_LABELS[quality],
        playedMoveEvalLabel=evaluation_label(played_eval_cp, played_mate),
        bestMoveLabel=best_label,
        bestMoveWasDifferent=best_different,
        explanation={
            "probableIdea": f"L'idée probable est de placer le {piece} en {to_square} pour améliorer son activité.",
            "whatItDoes": what_it_does,
            "whatItAllows": _what_it_allows(piece, to_square, board_after),
            "whatToWatch": _what_to_watch(piece, to_square),
            "comparisonWithBest": _comparison(best_label, best_different, quality),
        },
        connectionToPlan=connection,
        whatItAttacks=_attacked_squares(board_before, played_move),
        whatItDefends=[],
        whatItAllowsNext=_next_steps(piece, to_square),
        bestAlternative={
            "moveLabel": best_label,
            "whyBetterOrDifferent": _comparison(best_label, best_different, quality),
        },
        warning=_what_to_watch(piece, to_square),
    )


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
        return f"Depuis {to_square}, le Cavalier peut aider à contrôler le centre et préparer le roque."
    if piece == "Fou":
        return f"Depuis {to_square}, le Fou regarde une diagonale et aide les autres pièces à sortir."
    if piece == "Pion":
        return f"Le Pion en {to_square} peut soutenir une pièce ou attaquer une case centrale."
    if board_after.is_check():
        return "Ce coup crée aussi un échec, donc l'adversaire doit répondre tout de suite."
    return f"La pièce en {to_square} peut ensuite soutenir un plan plus large."


def _what_to_watch(piece: str, to_square: str) -> str:
    if piece == "Cavalier":
        return f"Ne déplace pas encore le Cavalier en {to_square} sans menace précise : développe aussi les autres pièces."
    if piece == "Pion":
        return f"Après ce Pion en {to_square}, regarde les cases qu'il ne défend plus derrière lui."
    return f"Vérifie que la pièce en {to_square} n'est pas attaquée gratuitement."


def _comparison(best_label: str, best_different: bool, quality: str) -> str:
    if not best_different:
        return "Le coup joué correspond au meilleur coup recommandé par l'analyse."
    if quality in {"excellent", "good", "playable"}:
        return f"Le moteur préférait {best_label}, mais le coup joué reste cohérent et instructif."
    return f"Le moteur préférait {best_label}. La différence vient d'une perte de coordination ou de sécurité dans la position."


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
            "Développer une autre pièce.",
            "Préparer le roque ou attaquer le centre.",
        ]
    if piece == "Pion":
        return [
            f"Utiliser le Pion en {to_square} pour soutenir le centre.",
            "Sortir une pièce mineure.",
            "Vérifier que le roi reste en sécurité.",
        ]
    return [f"Vérifier que la pièce en {to_square} est bien défendue.", "Chercher le prochain objectif du plan."]


def _connection_to_plan(move_history_pgn: str | None, move_uci: str) -> str:
    return "Ce coup est comparé au plan actif et aux principes de la position actuelle."
