from __future__ import annotations

import chess


def detect_game_phase(fen: str, move_history: list[str] | None = None, plan_active: bool = False) -> str:
    board = chess.Board(fen)
    history = move_history or []
    piece_count = len(board.piece_map())
    queens = sum(
        1
        for piece in board.piece_map().values()
        if piece.piece_type == chess.QUEEN
    )
    minor_home_count = _minor_home_count(board)

    if piece_count <= 12 or queens < 2:
        return "endgame"
    if plan_active and len(history) <= 14:
        return "opening"
    if len(history) <= 10 or minor_home_count >= 3:
        return "opening"
    if len(history) <= 18 and minor_home_count <= 2:
        return "transition"
    return "middlegame"


def _minor_home_count(board: chess.Board) -> int:
    homes = [chess.B1, chess.G1, chess.C1, chess.F1, chess.B8, chess.G8, chess.C8, chess.F8]
    return sum(1 for square in homes if board.piece_at(square) is not None)
