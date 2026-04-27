from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import chess


DATA_PATH = Path(__file__).parent / "data" / "beginner_openings.json"


def detect_game_phase(board: chess.Board) -> str:
    queens = sum(1 for square in chess.SQUARES if (piece := board.piece_at(square)) and piece.piece_type == chess.QUEEN)
    major_minor_count = sum(
        1
        for square in chess.SQUARES
        if (piece := board.piece_at(square)) and piece.piece_type in {chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN}
    )
    if queens < 2 or major_minor_count <= 8:
        return "endgame"
    if board.fullmove_number <= 10 or len(undeveloped_pieces(board)) >= 3:
        return "opening"
    return "middlegame"


def build_position_plan(fen: str, move_history_uci: list[str] | None = None) -> dict[str, Any]:
    board = chess.Board(fen)
    phase = detect_game_phase(board)
    opening = detect_opening(move_history_uci or [])

    return {
        "phase": phase,
        "phaseLabel": {"opening": "Ouverture", "middlegame": "Milieu de partie", "endgame": "Finale"}[phase],
        "detectedOpening": opening,
        "plan": phase_plan(phase),
        "nextObjective": next_objective(board, phase, opening),
        "positionContext": position_context(board),
    }


def position_context(board: chess.Board) -> dict[str, Any]:
    return {
        "phase": detect_game_phase(board),
        "centerPawns": describe_center_pawns(board),
        "kingSafety": describe_king_safety(board),
        "undevelopedPieces": undeveloped_pieces(board),
        "importantSquares": important_squares(board),
    }


def detect_opening(move_history_uci: list[str]) -> dict[str, Any] | None:
    if not move_history_uci:
        return None
    best_match: dict[str, Any] | None = None
    best_length = 0
    for opening in load_openings():
        typical = opening["typicalMoves"]
        match_length = 0
        for played, expected in zip(move_history_uci, typical):
            if played != expected:
                break
            match_length += 1
        if match_length > best_length and match_length >= 3:
            best_match = opening
            best_length = match_length
    return best_match


def phase_plan(phase: str) -> list[str]:
    if phase == "opening":
        return [
            "Développer les pièces mineures.",
            "Mettre le roi en sécurité.",
            "Attaquer ou défendre les cases centrales.",
        ]
    if phase == "middlegame":
        return [
            "Identifier la pièce la moins active.",
            "Chercher les menaces sur le roi adverse.",
            "Améliorer une pièce avant de lancer une attaque.",
        ]
    return [
        "Activer le roi.",
        "Créer ou arrêter un pion passé.",
        "Échanger les pièces quand cela simplifie une position gagnante.",
    ]


def next_objective(board: chess.Board, phase: str, opening: dict[str, Any] | None) -> str:
    if opening:
        return str(opening["beginnerGoal"])
    if phase == "opening":
        pieces = undeveloped_pieces(board)
        if pieces:
            return f"Développer {pieces[0]} sans affaiblir le roi."
        return "Roquer ou contester le centre."
    if phase == "middlegame":
        return "Trouver une cible concrète : roi, pion faible ou colonne ouverte."
    return "Rapprocher le roi du centre et pousser les pions passés."


def describe_center_pawns(board: chess.Board) -> str:
    descriptions = []
    for square_name in ["d4", "e4", "d5", "e5"]:
        piece = board.piece_at(chess.parse_square(square_name))
        if piece and piece.piece_type == chess.PAWN:
            side = "blancs" if piece.color == chess.WHITE else "noirs"
            descriptions.append(f"Les {side} ont un pion en {square_name}.")
    return " ".join(descriptions) if descriptions else "Aucun pion n'occupe encore directement d4, e4, d5 ou e5."


def describe_king_safety(board: chess.Board) -> str:
    white_king = board.king(chess.WHITE)
    black_king = board.king(chess.BLACK)
    white_safe = white_king in {chess.G1, chess.C1}
    black_safe = black_king in {chess.G8, chess.C8}
    if white_safe and black_safe:
        return "Les deux rois sont roqués."
    if white_safe:
        return "Le roi blanc est roqué, le roi noir ne l'est pas encore."
    if black_safe:
        return "Le roi noir est roqué, le roi blanc ne l'est pas encore."
    return "Les deux rois ne sont pas encore roqués."


def undeveloped_pieces(board: chess.Board) -> list[str]:
    pieces = []
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
    for square, label in homes.items():
        if board.piece_at(square):
            pieces.append(label)
    return pieces


def important_squares(board: chess.Board) -> list[str]:
    squares = ["e4", "d4", "e5", "d5"]
    if board.turn == chess.WHITE:
        squares.extend(["c4", "f4"])
    else:
        squares.extend(["c5", "f5"])
    return squares


@lru_cache(maxsize=1)
def load_openings() -> list[dict[str, Any]]:
    if not DATA_PATH.exists():
        return []
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))
