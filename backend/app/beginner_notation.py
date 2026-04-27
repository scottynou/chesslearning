from __future__ import annotations

from dataclasses import dataclass

import chess


PIECE_NAMES = {
    chess.PAWN: "Pion",
    chess.KNIGHT: "Cavalier",
    chess.BISHOP: "Fou",
    chess.ROOK: "Tour",
    chess.QUEEN: "Dame",
    chess.KING: "Roi",
}

PIECE_ICONS = {
    (chess.WHITE, chess.PAWN): "♙",
    (chess.WHITE, chess.KNIGHT): "♘",
    (chess.WHITE, chess.BISHOP): "♗",
    (chess.WHITE, chess.ROOK): "♖",
    (chess.WHITE, chess.QUEEN): "♕",
    (chess.WHITE, chess.KING): "♔",
    (chess.BLACK, chess.PAWN): "♟",
    (chess.BLACK, chess.KNIGHT): "♞",
    (chess.BLACK, chess.BISHOP): "♝",
    (chess.BLACK, chess.ROOK): "♜",
    (chess.BLACK, chess.QUEEN): "♛",
    (chess.BLACK, chess.KING): "♚",
}

FRENCH_SAN_REPLACEMENTS = {
    "N": "C",
    "B": "F",
    "R": "T",
    "Q": "D",
    "K": "R",
}


@dataclass(frozen=True)
class BeginnerMoveNotation:
    beginner_label: str
    short_label: str
    san: str
    french_san: str
    uci: str
    piece_name: str
    from_square: str
    to_square: str
    icon: str

    def as_dict(self) -> dict[str, str]:
        return {
            "beginnerLabel": self.beginner_label,
            "shortLabel": self.short_label,
            "san": self.san,
            "frenchSan": self.french_san,
            "uci": self.uci,
            "pieceName": self.piece_name,
            "from": self.from_square,
            "to": self.to_square,
            "icon": self.icon,
        }


def beginner_notation_for_uci(fen: str, move_uci: str, san: str | None = None) -> BeginnerMoveNotation:
    board = chess.Board(fen)
    move = chess.Move.from_uci(move_uci)
    if move not in board.legal_moves:
        # Some review contexts pass a move that was legal in fenBefore but not in a
        # later board. Keep the output useful instead of crashing.
        piece = board.piece_at(move.from_square)
    else:
        piece = board.piece_at(move.from_square)

    if piece is None:
        piece_name = "Pièce"
        icon = "•"
    else:
        piece_name = PIECE_NAMES[piece.piece_type]
        icon = PIECE_ICONS[(piece.color, piece.piece_type)]

    move_san = san or _safe_san(board, move)
    from_square = chess.square_name(move.from_square)
    to_square = chess.square_name(move.to_square)

    if piece and piece.piece_type == chess.KING and board.is_castling(move):
        side = "Petit" if chess.square_file(move.to_square) > chess.square_file(move.from_square) else "Grand"
        beginner_label = f"{side} roque : le roi se met en sécurité"
        short_label = f"{side} roque"
    else:
        beginner_label = f"{icon} {piece_name} {from_square} → {to_square}"
        short_label = f"{piece_name} → {to_square}"

    return BeginnerMoveNotation(
        beginner_label=beginner_label,
        short_label=short_label,
        san=move_san,
        french_san=french_san(move_san),
        uci=move_uci,
        piece_name=piece_name,
        from_square=from_square,
        to_square=to_square,
        icon=icon,
    )


def french_san(san: str) -> str:
    if san in {"O-O", "O-O+", "O-O#"}:
        return san
    if san in {"O-O-O", "O-O-O+", "O-O-O#"}:
        return san
    if not san:
        return san
    first = san[0]
    return FRENCH_SAN_REPLACEMENTS.get(first, first) + san[1:]


def _safe_san(board: chess.Board, move: chess.Move) -> str:
    try:
        return board.san(move)
    except Exception:
        return move.uci()
