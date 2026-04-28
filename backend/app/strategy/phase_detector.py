from __future__ import annotations

import chess


def detect_game_phase(fen: str, move_history: list[str] | None = None, plan_active: bool = False) -> str:
    board = chess.Board(fen)
    history = move_history or []
    piece_count = len(board.piece_map())
    non_king_piece_count = sum(1 for piece in board.piece_map().values() if piece.piece_type != chess.KING)
    material = sum(_piece_value(piece) for piece in board.piece_map().values())
    queens = sum(
        1
        for piece in board.piece_map().values()
        if piece.piece_type == chess.QUEEN
    )
    major_pieces = sum(
        1
        for piece in board.piece_map().values()
        if piece.piece_type in {chess.QUEEN, chess.ROOK}
    )
    minor_home_count = _minor_home_count(board)

    if board.is_game_over():
        return "endgame"
    if piece_count <= 12 or non_king_piece_count <= 10:
        return "endgame"
    if len(history) >= 16 and queens == 0 and (piece_count <= 16 or material <= 24):
        return "endgame"
    if len(history) >= 20 and major_pieces <= 2 and piece_count <= 18:
        return "endgame"
    if len(history) <= 8:
        return "opening"
    if len(history) <= 12 and minor_home_count >= 3:
        return "opening"
    if plan_active and len(history) <= 14 and minor_home_count >= 2 and queens == 2:
        return "opening"
    if len(history) <= 18 and minor_home_count <= 2:
        return "transition"
    return "middlegame"


def _minor_home_count(board: chess.Board) -> int:
    homes = [chess.B1, chess.G1, chess.C1, chess.F1, chess.B8, chess.G8, chess.C8, chess.F8]
    return sum(1 for square in homes if board.piece_at(square) is not None)


def _piece_value(piece: chess.Piece) -> int:
    return {
        chess.PAWN: 1,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
        chess.KING: 0,
    }[piece.piece_type]
