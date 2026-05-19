from __future__ import annotations

import chess


def analyze_endgame(fen: str) -> dict[str, object]:
    """
    Phase de finale : on garde uniquement le marqueur de phase et le
    comptage de pieces (utile pour decider les bandes d'accuracy et les
    seuils de pression de nulle). Pas de cours ecrit ; les conseils
    viennent du moteur via les recommandations de coups.
    """
    board = chess.Board(fen)
    piece_count = len(board.piece_map())
    return {
        "phase": "endgame",
        "pieceCount": piece_count,
    }
