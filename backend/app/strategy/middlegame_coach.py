from __future__ import annotations

import chess


def analyze_middlegame(fen: str) -> dict[str, object]:
    board = chess.Board(fen)
    priorities = []
    candidate_plans = []

    if board.is_check():
        priorities.append("Ton roi est en échec : réponds à cette menace avant tout.")
    else:
        priorities.append("Vérifie que ton roi reste en sécurité avant de chercher une attaque.")

    hanging = hanging_pieces(board)
    if hanging:
        priorities.append(f"Pièces non défendues à surveiller : {', '.join(hanging[:3])}.")
    undeveloped = undeveloped_pieces(board)
    if undeveloped:
        priorities.append(f"Pièce à améliorer : {undeveloped[0]}.")

    open_files = detect_open_files(board)
    if open_files:
        candidate_plans.append(
            {
                "name": "Mettre une tour sur une colonne ouverte",
                "why": f"Une tour devient plus forte sur une colonne sans pion, comme la colonne {open_files[0]}.",
            }
        )
    candidate_plans.append(
        {
            "name": "Améliorer la pire pièce",
            "why": "Une pièce active crée plus de menaces et défend mieux ton roi.",
        }
    )
    candidate_plans.append(
        {
            "name": "Attaquer une faiblesse",
            "why": "Un pion isolé, une pièce clouée ou une case faible donne un objectif concret.",
        }
    )

    return {
        "phase": "Milieu de jeu",
        "mainGoal": "Améliorer les pièces et éviter les gaffes.",
        "currentPriorities": priorities[:4],
        "candidatePlans": candidate_plans[:3],
        "checklist": [
            "Est-ce que mon roi est en danger ?",
            "Est-ce que je peux gagner du matériel tout de suite ?",
            "Est-ce que l'adversaire menace quelque chose ?",
            "Quelle est ma pire pièce ?",
            "Puis-je occuper une colonne ouverte avec une tour ?",
        ],
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
