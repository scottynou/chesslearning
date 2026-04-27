from __future__ import annotations

import chess

from .beginner_notation import beginner_notation_for_uci


def translate_pv(fen: str, pv: list[str], limit: int = 5) -> list[dict[str, object]]:
    board = chess.Board(fen)
    translated: list[dict[str, object]] = []

    for index, move_uci in enumerate(pv[:limit], start=1):
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            continue
        if move not in board.legal_moves:
            break

        san = board.san(move)
        notation = beginner_notation_for_uci(board.fen(), move_uci, san)
        translated.append(
            {
                "moveNumber": index,
                "side": "white" if board.turn == chess.WHITE else "black",
                "beginnerLabel": notation.beginner_label,
                "simpleExplanation": simple_move_explanation(board, move),
            }
        )
        board.push(move)

    return translated


def plan_ideas_from_pv(fen: str, pv: list[str], limit: int = 4) -> list[str]:
    items = translate_pv(fen, pv, limit=limit)
    ideas: list[str] = []
    for item in items:
        idea = str(item["simpleExplanation"])
        if idea not in ideas:
            ideas.append(idea)
    return ideas[:limit]


def simple_move_explanation(board: chess.Board, move: chess.Move) -> str:
    piece = board.piece_at(move.from_square)
    to_square = chess.square_name(move.to_square)
    from_square = chess.square_name(move.from_square)

    if piece is None:
        return "Le coup améliore la position sans perdre de matériel."

    if board.is_castling(move):
        return "Le roi se met en sécurité et les tours pourront mieux participer."

    if board.is_capture(move):
        return f"La pièce prend en {to_square} et change l'équilibre matériel."

    if piece.piece_type == chess.KNIGHT:
        center_targets = _attacked_center_squares(move.to_square)
        if center_targets:
            return f"Le cavalier va de {from_square} à {to_square} et contrôle {', '.join(center_targets)}."
        return f"Le cavalier va de {from_square} à {to_square} pour se rapprocher du centre."

    if piece.piece_type == chess.BISHOP:
        return f"Le fou sort de {from_square} vers {to_square} et ouvre une diagonale active."

    if piece.piece_type == chess.PAWN:
        if to_square in {"d4", "e4", "d5", "e5"}:
            return f"Le pion va en {to_square} pour occuper le centre."
        if to_square in {"c4", "c5", "f4", "f5"}:
            return f"Le pion va en {to_square} pour attaquer ou soutenir le centre."
        return f"Le pion avance de {from_square} à {to_square} pour soutenir les pièces."

    if piece.piece_type == chess.QUEEN:
        return f"La dame va en {to_square}; il faut vérifier qu'elle ne devient pas une cible."

    if piece.piece_type == chess.ROOK:
        return f"La tour va en {to_square} pour occuper une colonne ou défendre une pièce."

    if piece.piece_type == chess.KING:
        return f"Le roi va en {to_square}; vérifie toujours sa sécurité."

    return "Le coup améliore la coordination des pièces."


def _attacked_center_squares(square: chess.Square) -> list[str]:
    attacked = []
    for target in chess.SquareSet(chess.BB_KNIGHT_ATTACKS[square]):
        name = chess.square_name(target)
        if name in {"d4", "e4", "d5", "e5", "c4", "c5", "f4", "f5"}:
            attacked.append(name)
    return attacked
