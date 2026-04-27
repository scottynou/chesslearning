from __future__ import annotations

import chess


def analyze_endgame(fen: str) -> dict[str, object]:
    board = chess.Board(fen)
    piece_count = len(board.piece_map())
    has_syzygy = False

    return {
        "phase": "Finale",
        "mainGoal": "Convertir l'avantage sans donner de contre-jeu.",
        "tablebaseAvailable": has_syzygy and piece_count <= 7,
        "conversionPlan": [
            "Activer le roi.",
            "Créer ou bloquer un pion passé.",
            "Pousser le pion seulement quand il est soutenu.",
            "Échanger les pièces si cela simplifie vers une finale gagnante.",
        ],
        "danger": "Attention au pat, aux échecs perpétuels et au roi adverse qui bloque ton pion.",
    }
