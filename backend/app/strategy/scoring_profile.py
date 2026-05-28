"""
Donnees pures pour le scoring : bandes d'accuracy, modulateurs de style,
facteur de crise. Extrait de plan_engine.py pour clarifier la responsabilite
(et permettre d'etre teste sans charger la stack Stockfish/Maia/AI).
"""
from __future__ import annotations

from typing import Any


def accuracy_bands_for_profile(human_profile: str | None, elo: int) -> dict[str, dict[str, int]]:
    """
    Bandes d'accuracy cibles par profil humain.
    lambda  → accuracy chess.com cible ~70% (max 75%)
    strong  → accuracy chess.com cible ~75% (max 78%)
    veryStrong → accuracy chess.com cible ~82-85% (max 85%)
    En cas de crise (position perdante/nulle), le debridage progressif via
    compute_crisis_factor interpolera ces bandes vers "survival" automatiquement.
    """
    # Approximation CAPS2/Chess.com : 800~72, 1500~79, 2000~84.
    # Le profil 3000 reste a 88 pour conserver l'humanisation elite existante.
    profile = human_profile or ("beginner" if elo < 1100 else "lambda" if elo < 1700 else "strong" if elo < 2600 else "veryStrong")

    if profile == "beginner":
        return {
            "normal":          {"target": 72, "min": 64, "max": 80, "planTolerance": 7},
            "favorable":       {"target": 70, "min": 62, "max": 78, "planTolerance": 7},
            "pressure":        {"target": 82, "min": 74, "max": 89, "planTolerance": 4},
            "strong_pressure": {"target": 86, "min": 78, "max": 92, "planTolerance": 3},
            "elite_pressure":  {"target": 89, "min": 82, "max": 95, "planTolerance": 2},
            "draw_warning":    {"target": 80, "min": 72, "max": 88, "planTolerance": 4},
            "draw_critical":   {"target": 90, "min": 83, "max": 96, "planTolerance": 2},
            "conversion":      {"target": 76, "min": 68, "max": 84, "planTolerance": 5},
            "survival":        {"target": 97, "min": 92, "max": 100, "planTolerance": 0},
        }

    if profile == "lambda":
        return {
            "normal":          {"target": 79, "min": 72, "max": 86, "planTolerance": 4},
            "favorable":       {"target": 78, "min": 71, "max": 85, "planTolerance": 4},
            "pressure":        {"target": 86, "min": 79, "max": 92, "planTolerance": 3},
            "strong_pressure": {"target": 88, "min": 81, "max": 94, "planTolerance": 2},
            "elite_pressure":  {"target": 91, "min": 85, "max": 96, "planTolerance": 2},
            "draw_warning":    {"target": 85, "min": 78, "max": 92, "planTolerance": 3},
            "draw_critical":   {"target": 92, "min": 86, "max": 97, "planTolerance": 1},
            "conversion":      {"target": 81, "min": 74, "max": 88, "planTolerance": 3},
            "survival":        {"target": 97, "min": 92, "max": 100, "planTolerance": 0},
        }

    if profile == "strong":
        return {
            "normal":          {"target": 84, "min": 77, "max": 90, "planTolerance": 3},
            "favorable":       {"target": 82, "min": 75, "max": 88, "planTolerance": 3},
            "pressure":        {"target": 90, "min": 83, "max": 95, "planTolerance": 2},
            "strong_pressure": {"target": 92, "min": 86, "max": 97, "planTolerance": 1},
            "elite_pressure":  {"target": 94, "min": 89, "max": 98, "planTolerance": 1},
            "draw_warning":    {"target": 91, "min": 85, "max": 96, "planTolerance": 2},
            "draw_critical":   {"target": 94, "min": 89, "max": 98, "planTolerance": 1},
            "conversion":      {"target": 86, "min": 79, "max": 92, "planTolerance": 2},
            "survival":        {"target": 98, "min": 94, "max": 100, "planTolerance": 0},
        }

    # veryStrong (baseElo=3000 → elite humanization active >=2800)
    return {
        "normal":          {"target": 88, "min": 82, "max": 93, "planTolerance": 4},
        "favorable":       {"target": 86, "min": 80, "max": 91, "planTolerance": 4},
        "pressure":        {"target": 93, "min": 88, "max": 97, "planTolerance": 2},
        "strong_pressure": {"target": 95, "min": 90, "max": 98, "planTolerance": 1},
        "elite_pressure":  {"target": 96, "min": 92, "max": 99, "planTolerance": 1},
        "draw_warning":    {"target": 93, "min": 88, "max": 97, "planTolerance": 2},
        "draw_critical":   {"target": 96, "min": 91, "max": 99, "planTolerance": 1},
        "conversion":      {"target": 91, "min": 85, "max": 95, "planTolerance": 2},
        "survival":        {"target": 99, "min": 96, "max": 100, "planTolerance": 0},
    }


def coach_style_modifiers(coach_style: str) -> dict[str, float]:
    """
    Modulateurs appliques au score final selon le style du coach.
    Style != niveau ELO : a niveau egal, un coach 'aggressive' poussera
    vers des coups plus tranchants, 'solid' vers la securite, etc.
    En cas de crise (crisis_factor > 0.5) ces modulateurs sont attenues
    automatiquement par le scoring pour ne pas contrarier la survie/victoire.
    """
    if coach_style == "aggressive":
        return {"risk_mul": 0.30, "simplicity_bonus": -0.05, "distance_relax": 0.0, "creative_rank_bonus": 0.0}
    if coach_style == "solid":
        return {"risk_mul": 0.85, "simplicity_bonus": 0.10, "distance_relax": 0.0, "creative_rank_bonus": 0.0}
    if coach_style == "creative":
        return {"risk_mul": 0.45, "simplicity_bonus": -0.06, "distance_relax": 0.22, "creative_rank_bonus": 8.0}
    if coach_style == "educational":
        return {"risk_mul": 0.62, "simplicity_bonus": 0.16, "distance_relax": 0.0, "creative_rank_bonus": 0.0}
    return {"risk_mul": 0.50, "simplicity_bonus": 0.0, "distance_relax": 0.0, "creative_rank_bonus": 0.0}


def compute_crisis_factor(
    position_score: int,
    mating_danger: str,
    draw_pressure: dict[str, Any],
    side_to_move_expected_percent: float | None = None,
) -> float:
    """
    Retourne un facteur 0.0 -> 1.0 pour le debridage progressif.
    0.0 = jeu normal avec caps d'accuracy et humanisation complete.
    1.0 = situation critique, survie pure, humanisation desactivee.
    Les bandes sont interpolees vers 'survival' proportionnellement.
    """
    if mating_danger == "critical":
        return 1.0

    if side_to_move_expected_percent is not None:
        expected = max(0.0, min(100.0, float(side_to_move_expected_percent)))
        if expected >= 45.0:
            expected_base = 0.0
        elif expected >= 38.0:
            expected_base = (45.0 - expected) / 7.0 * 0.30
        elif expected >= 32.0:
            expected_base = 0.30 + (38.0 - expected) / 6.0 * 0.35
        elif expected >= 24.0:
            expected_base = 0.65 + (32.0 - expected) / 8.0 * 0.30
        else:
            expected_base = 1.0
    else:
        expected_base = 0.0

    if position_score >= -80:
        cp_base = 0.0
    elif position_score >= -150:
        cp_base = ((-80) - position_score) / 70.0 * 0.25
    elif position_score >= -260:
        cp_base = 0.25 + ((-150) - position_score) / 110.0 * 0.50
    elif position_score >= -400:
        cp_base = 0.75 + ((-260) - position_score) / 140.0 * 0.25
    else:
        cp_base = 1.0

    base = max(expected_base, cp_base)

    draw_level = str((draw_pressure or {}).get("level", "none"))
    draw_bonus = {"none": 0.0, "warning": 0.12, "critical": 0.28}.get(draw_level, 0.0)

    return min(1.0, base + draw_bonus)
