"""
Math utilities for chess accuracy. No external dependencies — safe to
import in tests without the full app stack (Stockfish, AI providers, etc.).
"""
from __future__ import annotations

import math


def cp_to_win_percent(cp: int) -> float:
    """
    Convertit une evaluation Stockfish en pourcentage de chances de gain
    (0-100), du point de vue de la couleur au trait.
    """
    capped = max(-1500, min(1500, cp))
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * capped)) - 1.0)


def move_accuracy_percent(cp_best: int, cp_played: int) -> float:
    """
    Formule d'accuracy Lichess par coup (0-100).
    """
    win_best = cp_to_win_percent(cp_best)
    win_played = cp_to_win_percent(cp_played)
    win_loss = max(0.0, win_best - win_played)
    raw = 103.1668 * math.exp(-0.04354 * win_loss) - 3.1669
    return max(0.0, min(100.0, raw))
