from __future__ import annotations

import chess


def analyze_middlegame(fen: str) -> dict[str, object]:
    """
    Phase de milieu de jeu : on garde uniquement les signaux analytiques
    (pieces en prise, colonnes ouvertes, pieces non developpees) sans
    generer de cours ecrit. Les conseils concrets viennent du moteur via
    les recommandations de coups, pas d'un script.
    """
    board = chess.Board(fen)
    return {
        "phase": "middlegame",
        "signals": {
            "inCheck": board.is_check(),
            "hangingPieces": hanging_pieces(board)[:5],
            "undevelopedPieces": undeveloped_pieces(board)[:4],
            "openFiles": detect_open_files(board),
        },
    }


def detect_open_files(board: chess.Board) -> list[str]:
    files = []
    for file_index, file_name in enumerate("abcdefgh"):
        has_pawn = any(
            (piece := board.piece_at(chess.square(file_index, rank))) and piece.piece_type == chess.PAWN
            for rank in range(8)
        )
        if not has_pawn:
            files.append(file_name)
    return files


def undeveloped_pieces(board: chess.Board) -> list[str]:
    homes = {
        chess.B1: "Cavalier b1",
        chess.G1: "Cavalier g1",
        chess.C1: "Fou c1",
        chess.F1: "Fou f1",
        chess.B8: "Cavalier b8",
        chess.G8: "Cavalier g8",
        chess.C8: "Fou c8",
        chess.F8: "Fou f8",
    }
    return [label for square, label in homes.items() if board.piece_at(square)]


def hanging_pieces(board: chess.Board) -> list[str]:
    result = []
    for square, piece in board.piece_map().items():
        attackers = board.attackers(not piece.color, square)
        defenders = board.attackers(piece.color, square)
        if attackers and not defenders and piece.piece_type != chess.KING:
            color = "blanc" if piece.color == chess.WHITE else "noir"
            result.append(f"{piece.symbol().upper()} {chess.square_name(square)} ({color})")
    return result
