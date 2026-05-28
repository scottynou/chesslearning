from __future__ import annotations

import math
from statistics import mean
from typing import Any

from .accuracy_math import score_to_expected_percent
from .strategy.plan_engine import (
    candidate_eval_cp,
    humanization_score_for_item,
    shape_recommendations_for_accuracy,
)
from .strategy.scoring_profile import accuracy_bands_for_profile, coach_style_modifiers


PROFILES = [
    ("beginner", 800, "Debutant 800"),
    ("lambda", 1500, "Humain 1500"),
    ("strong", 2000, "Humain 2000"),
    ("veryStrong", 3000, "Elite 3000"),
]

STYLES = [
    ("balanced", "Equilibre"),
    ("aggressive", "Agressif"),
    ("solid", "Solide"),
    ("creative", "Creatif"),
    ("educational", "Pedagogique"),
]

STYLE_WIN_ADJUSTMENT = {
    "balanced": 0,
    "aggressive": 22,
    "solid": 8,
    "creative": -4,
    "educational": -12,
}

STYLE_HUMAN_ADJUSTMENT = {
    "balanced": 0,
    "aggressive": -3,
    "solid": 3,
    "creative": 4,
    "educational": 5,
}


def build_calibration_report(opponent_elo: int = 1600) -> dict[str, Any]:
    opponent = max(800, min(2600, int(opponent_elo)))
    rows = []
    for profile, elo, profile_label in PROFILES:
        for style, style_label in STYLES:
            rows.append(_calibrate_row(profile, profile_label, elo, style, style_label, opponent))

    best_by_profile = {}
    for profile, _elo, _label in PROFILES:
        profile_rows = [row for row in rows if row["profile"] == profile]
        best = max(profile_rows, key=lambda row: row["winRateVsOpponent"] + row["humanizationScore"] * 0.28)
        best_by_profile[profile] = best["style"]

    return {
        "opponentElo": opponent,
        "methodology": (
            "Proxy deterministe: les combinaisons profil/style sont rejouees sur des suites types "
            "avec le scoring backend actuel. Le winrate n'est pas encore du self-play complet."
        ),
        "sampleCount": len(CALIBRATION_SUITES),
        "rows": rows,
        "bestByProfile": best_by_profile,
    }


def _calibrate_row(
    profile: str,
    profile_label: str,
    elo: int,
    style: str,
    style_label: str,
    opponent_elo: int,
) -> dict[str, Any]:
    selected_moves = []
    cp_losses = []
    top_engine_count = 0
    position_win_rates = []

    for suite in CALIBRATION_SUITES:
        band = accuracy_bands_for_profile(profile, elo)[suite["bandKey"]]
        scoring_profile = {
            "mode": suite["mode"],
            "humanProfile": profile,
            "targetElo": elo,
            "coachStyle": style,
            "styleModifiers": coach_style_modifiers(style),
            "drawPressure": suite.get("drawPressure", {"level": "none"}),
            **band,
        }
        shaped = shape_recommendations_for_accuracy(list(suite["candidates"]), scoring_profile)
        selected = shaped[0]
        selected_moves.append(selected)
        cp_losses.append(max(0, int(suite["bestEvalCp"]) - candidate_eval_cp(selected)))
        if int(selected.get("engineRank") or 99) == 1:
            top_engine_count += 1
        position_win_rates.append(
            score_to_expected_percent(
                eval_cp=candidate_eval_cp(selected),
                mate_in=selected.get("candidate", {}).get("mateIn") if isinstance(selected.get("candidate"), dict) else None,
                wdl=selected.get("candidate", {}).get("wdl") if isinstance(selected.get("candidate"), dict) else None,
            )
        )

    average_engine_score = mean(int(move.get("engineScore") or 0) for move in selected_moves)
    average_risk = mean(int(move.get("tacticalRisk") or 0) for move in selected_moves)
    average_cp_loss = mean(cp_losses)
    top_engine_rate = top_engine_count / len(selected_moves)
    target_band = accuracy_bands_for_profile(profile, elo)["normal"]
    humanization = mean(humanization_score_for_item(move, {"coachStyle": style, **target_band}) for move in selected_moves)
    humanization = max(0, min(100, round(humanization + STYLE_HUMAN_ADJUSTMENT[style])))
    performance_elo = _estimate_performance_elo(
        base_elo=elo,
        average_engine_score=average_engine_score,
        average_cp_loss=average_cp_loss,
        average_risk=average_risk,
        top_engine_rate=top_engine_rate,
        style=style,
    )
    win_rate_vs_opponent = _blended_win_rate(
        elo=elo,
        performance_elo=performance_elo,
        opponent_elo=opponent_elo,
        position_win_chance=mean(position_win_rates),
    )

    return {
        "profile": profile,
        "profileLabel": profile_label,
        "elo": elo,
        "style": style,
        "styleLabel": style_label,
        "targetAccuracy": target_band["target"],
        "minAccuracy": target_band["min"],
        "maxAccuracy": target_band["max"],
        "humanizationScore": humanization,
        "winRateVsOpponent": round(max(5.0, min(96.0, win_rate_vs_opponent)), 1),
        "positionWinChance": round(mean(position_win_rates), 1),
        "averageEngineScore": round(average_engine_score, 1),
        "averageCpLoss": round(average_cp_loss),
        "topEngineMoveRate": round(top_engine_rate * 100, 1),
        "sampleCount": len(selected_moves),
        "recommendation": _recommendation_for(humanization, win_rate_vs_opponent, style),
    }


def _estimate_performance_elo(
    *,
    base_elo: int,
    average_engine_score: float,
    average_cp_loss: float,
    average_risk: float,
    top_engine_rate: float,
    style: str,
) -> float:
    return (
        base_elo
        + (average_engine_score - 75.0) * 16.0
        - average_cp_loss * 0.42
        - max(0.0, average_risk - 18.0) * 1.7
        + top_engine_rate * 55.0
        + STYLE_WIN_ADJUSTMENT[style]
    )


def _elo_expected_score(player_elo: float, opponent_elo: int) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (opponent_elo - player_elo) / 400.0))


def _blended_win_rate(*, elo: int, performance_elo: float, opponent_elo: int, position_win_chance: float) -> float:
    elo_proxy = _elo_expected_score(performance_elo, opponent_elo) * 100
    if elo >= 2800:
        elo_weight = 0.93
    elif elo >= 1900:
        elo_weight = 0.76
    else:
        elo_weight = 0.62
    return elo_proxy * elo_weight + position_win_chance * (1.0 - elo_weight)


def _recommendation_for(humanization: int, win_rate: float, style: str) -> str:
    if humanization >= 82 and win_rate >= 62:
        return "Meilleur compromis actuel."
    if style == "aggressive" and win_rate >= 58:
        return "Bon pour maximiser le gain, a surveiller en positions tactiques."
    if style == "solid" and humanization >= 82:
        return "Tres sain pour garder le cote humain sans trop perdre de force."
    if style == "creative":
        return "Plus surprenant, utile si la perte de winrate reste acceptable."
    if style == "educational":
        return "Lisible et humain, moins oriente performance pure."
    return "Profil stable, bon point de depart pour la calibration."


def _candidate(
    move: str,
    *,
    rank: int,
    engine_score: int,
    eval_cp: int,
    plan_fit: int,
    simplicity: int,
    risk: int,
    final_score: int,
    source: str = "engine",
) -> dict[str, Any]:
    return {
        "moveUci": move,
        "source": source,
        "engineRank": rank,
        "planFitScore": plan_fit,
        "engineScore": engine_score,
        "beginnerSimplicityScore": simplicity,
        "tacticalRisk": risk,
        "finalCoachScore": final_score,
        "warning": None,
        "candidate": {"evalCp": eval_cp, "mateIn": None},
    }


CALIBRATION_SUITES: list[dict[str, Any]] = [
    {
        "name": "calm_plan",
        "mode": "normal",
        "bandKey": "normal",
        "bestEvalCp": 180,
        "candidates": [
            _candidate("best", rank=1, engine_score=100, eval_cp=180, plan_fit=45, simplicity=48, risk=14, final_score=90),
            _candidate("near_best", rank=2, engine_score=93, eval_cp=145, plan_fit=58, simplicity=62, risk=16, final_score=88),
            _candidate("human_plan", rank=3, engine_score=86, eval_cp=108, plan_fit=94, simplicity=84, risk=8, final_score=88, source="plan_and_engine"),
            _candidate("natural", rank=4, engine_score=81, eval_cp=72, plan_fit=72, simplicity=90, risk=6, final_score=82),
        ],
    },
    {
        "name": "sharp_choice",
        "mode": "normal",
        "bandKey": "normal",
        "bestEvalCp": 165,
        "candidates": [
            _candidate("engine_tactic", rank=1, engine_score=100, eval_cp=165, plan_fit=40, simplicity=46, risk=26, final_score=88),
            _candidate("sharp_human", rank=2, engine_score=91, eval_cp=132, plan_fit=62, simplicity=55, risk=28, final_score=90),
            _candidate("practical", rank=3, engine_score=87, eval_cp=108, plan_fit=68, simplicity=74, risk=13, final_score=86),
            _candidate("safe_develop", rank=4, engine_score=84, eval_cp=92, plan_fit=72, simplicity=88, risk=6, final_score=82),
        ],
    },
    {
        "name": "under_pressure",
        "mode": "pressure",
        "bandKey": "pressure",
        "bestEvalCp": 70,
        "candidates": [
            _candidate("only_defense", rank=1, engine_score=100, eval_cp=70, plan_fit=38, simplicity=42, risk=20, final_score=91),
            _candidate("human_defense", rank=2, engine_score=91, eval_cp=36, plan_fit=62, simplicity=72, risk=15, final_score=88),
            _candidate("soft_defense", rank=4, engine_score=80, eval_cp=-22, plan_fit=78, simplicity=86, risk=8, final_score=80),
        ],
    },
    {
        "name": "conversion",
        "mode": "conversion",
        "bandKey": "conversion",
        "bestEvalCp": 420,
        "candidates": [
            _candidate("clean_win", rank=1, engine_score=100, eval_cp=420, plan_fit=55, simplicity=58, risk=14, final_score=94),
            _candidate("practical_win", rank=2, engine_score=94, eval_cp=330, plan_fit=76, simplicity=78, risk=8, final_score=92),
            _candidate("human_conversion", rank=3, engine_score=88, eval_cp=250, plan_fit=86, simplicity=88, risk=6, final_score=88),
        ],
    },
    {
        "name": "draw_break",
        "mode": "draw_break",
        "bandKey": "draw_warning",
        "drawPressure": {"level": "warning", "spreadCp": 34},
        "bestEvalCp": 92,
        "candidates": [
            _candidate("flat_best", rank=1, engine_score=96, eval_cp=20, plan_fit=42, simplicity=82, risk=5, final_score=86),
            _candidate("active_try", rank=2, engine_score=91, eval_cp=92, plan_fit=68, simplicity=66, risk=18, final_score=88),
            _candidate("quiet_human", rank=3, engine_score=85, eval_cp=35, plan_fit=76, simplicity=88, risk=6, final_score=82),
        ],
    },
]
