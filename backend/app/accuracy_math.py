"""
Math utilities for chess accuracy. No external dependencies — safe to
import in tests without the full app stack (Stockfish, AI providers, etc.).
"""
from __future__ import annotations

import math


def clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def cp_to_win_percent(cp: int) -> float:
    """
    Convertit une evaluation Stockfish en pourcentage de chances de gain
    (0-100), du point de vue de la couleur au trait.
    """
    capped = max(-1500, min(1500, cp))
    return clamp_percent(50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * capped)) - 1.0))


def wdl_to_expected_percent(wdl: tuple[int, int, int] | list[int] | None) -> float | None:
    """
    Convertit un triplet Stockfish WDL en score attendu (0-100).

    Stockfish exprime W/D/L en millièmes depuis le point de vue du moteur
    courant. Pour une jauge "winrate" utilisable aux echecs, on affiche le
    score attendu plutot que la probabilite stricte de victoire : une nulle
    vaut donc 0.5.
    """
    if not wdl or len(wdl) != 3:
        return None
    wins, draws, losses = (max(0, int(value)) for value in wdl)
    total = wins + draws + losses
    if total <= 0:
        return None
    return clamp_percent((wins + draws * 0.5) * 100.0 / total)


def mate_to_expected_percent(mate_in: int) -> float:
    distance = max(1, abs(int(mate_in)))
    certainty = max(96.0, 99.8 - min(distance - 1, 10) * 0.32)
    return certainty if mate_in > 0 else 100.0 - certainty


def score_to_expected_percent(
    *,
    eval_cp: int | None,
    mate_in: int | None = None,
    wdl: tuple[int, int, int] | list[int] | None = None,
) -> float:
    wdl_percent = wdl_to_expected_percent(wdl)
    if wdl_percent is not None:
        return wdl_percent
    if mate_in is not None:
        return mate_to_expected_percent(mate_in)
    if eval_cp is None:
        return 50.0
    return cp_to_win_percent(int(eval_cp))


def expected_loss_accuracy_percent(best_expected: float, played_expected: float) -> float:
    win_loss = max(0.0, clamp_percent(best_expected) - clamp_percent(played_expected))
    raw = 100.0 - 4.45 * (win_loss ** 0.72)
    return clamp_percent(raw)


def move_accuracy_percent(
    cp_best: int | None,
    cp_played: int | None,
    *,
    mate_best: int | None = None,
    mate_played: int | None = None,
    wdl_best: tuple[int, int, int] | list[int] | None = None,
    wdl_played: tuple[int, int, int] | list[int] | None = None,
) -> float:
    """
    Approximation CAPS2/Chess.com par coup (0-100).

    Chess.com ne publie pas la formule exacte de CAPS2. On reprend le meme
    principe public : comparer le coup joue au meilleur coup moteur via la
    perte d'esperance de gain, puis projeter cette perte sur une note
    "scolaire" ou la plupart des parties humaines restent entre 50 et 95.
    """
    best_expected = score_to_expected_percent(eval_cp=cp_best, mate_in=mate_best, wdl=wdl_best)
    played_expected = score_to_expected_percent(eval_cp=cp_played, mate_in=mate_played, wdl=wdl_played)
    return expected_loss_accuracy_percent(best_expected, played_expected)
