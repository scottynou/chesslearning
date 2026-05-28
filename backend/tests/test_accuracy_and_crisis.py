from app.accuracy_math import cp_to_win_percent, move_accuracy_percent
from app.strategy.scoring_profile import (
    accuracy_bands_for_profile,
    coach_style_modifiers,
    compute_crisis_factor,
)


def test_cp_to_win_percent_is_50_when_balanced():
    assert abs(cp_to_win_percent(0) - 50.0) < 0.01


def test_cp_to_win_percent_higher_for_positive_eval():
    assert cp_to_win_percent(200) > cp_to_win_percent(0)
    assert cp_to_win_percent(800) > cp_to_win_percent(200)


def test_cp_to_win_percent_is_capped():
    # Tres gros avantages ou desavantages restent dans [0, 100]
    assert 0.0 <= cp_to_win_percent(-5000) <= 100.0
    assert 0.0 <= cp_to_win_percent(5000) <= 100.0


def test_move_accuracy_is_100_when_no_loss():
    assert abs(move_accuracy_percent(50, 50) - 100.0) < 0.01


def test_move_accuracy_drops_with_loss():
    perfect = move_accuracy_percent(100, 100)
    small_loss = move_accuracy_percent(100, 50)
    big_loss = move_accuracy_percent(100, -200)
    assert perfect > small_loss > big_loss
    assert small_loss > 80
    assert 45 <= big_loss <= 75


def test_move_accuracy_uses_wdl_when_available():
    accurate = move_accuracy_percent(0, 0, wdl_best=[650, 300, 50], wdl_played=[620, 310, 70])
    losing = move_accuracy_percent(0, 0, wdl_best=[650, 300, 50], wdl_played=[80, 240, 680])
    assert accurate > 90
    assert losing < 45


def test_move_accuracy_handles_mate_swings_explicitly():
    keeps_mate = move_accuracy_percent(None, None, mate_best=3, mate_played=4)
    misses_mate = move_accuracy_percent(None, None, mate_best=3, mate_played=-3)
    assert keeps_mate > 95
    assert misses_mate < 20


def test_accuracy_bands_target_descend_with_profile_quality():
    """
    Cibles attendues : beginner ~72%, lambda ~79%, strong ~84%, veryStrong ~88%.
    Verifier l'ordre croissant des cibles "normal" entre profils.
    """
    beginner_bands = accuracy_bands_for_profile("beginner", 800)
    lambda_bands = accuracy_bands_for_profile("lambda", 1500)
    strong_bands = accuracy_bands_for_profile("strong", 2000)
    very_strong_bands = accuracy_bands_for_profile("veryStrong", 3000)
    assert beginner_bands["normal"]["target"] < lambda_bands["normal"]["target"]
    assert lambda_bands["normal"]["target"] < strong_bands["normal"]["target"]
    assert strong_bands["normal"]["target"] < very_strong_bands["normal"]["target"]


def test_accuracy_bands_beginner_is_low_but_not_blunder_friendly():
    bands = accuracy_bands_for_profile("beginner", 800)
    assert 70 <= bands["normal"]["target"] <= 74
    assert bands["normal"]["min"] >= 64
    assert bands["normal"]["max"] <= 80


def test_accuracy_bands_lambda_target_around_79():
    bands = accuracy_bands_for_profile("lambda", 1500)
    assert 77 <= bands["normal"]["target"] <= 81
    assert bands["normal"]["max"] <= 86  # reste humain, mais plus competitif


def test_survival_band_is_strict_for_all_profiles():
    for profile in ("beginner", "lambda", "strong", "veryStrong"):
        bands = accuracy_bands_for_profile(profile, 1500)
        assert bands["survival"]["target"] >= 97
        assert bands["survival"]["min"] >= 92


def test_crisis_factor_zero_when_position_is_fine():
    factor = compute_crisis_factor(
        position_score=20,
        mating_danger="none",
        draw_pressure={"level": "none"},
    )
    assert factor == 0.0


def test_crisis_factor_one_when_mate_threat():
    factor = compute_crisis_factor(
        position_score=-50,
        mating_danger="critical",
        draw_pressure={"level": "none"},
    )
    assert factor == 1.0


def test_crisis_factor_grows_smoothly_with_position_loss():
    f0 = compute_crisis_factor(0, "none", {"level": "none"})
    f1 = compute_crisis_factor(-100, "none", {"level": "none"})
    f2 = compute_crisis_factor(-200, "none", {"level": "none"})
    f3 = compute_crisis_factor(-300, "none", {"level": "none"})
    assert f0 < f1 < f2 < f3
    assert 0.0 <= f0 <= 0.05
    assert 0.05 <= f1 <= 0.30
    assert 0.30 <= f2 <= 0.80
    assert 0.80 <= f3 <= 1.0


def test_draw_pressure_pushes_crisis_higher():
    no_draw = compute_crisis_factor(-100, "none", {"level": "none"})
    with_warning = compute_crisis_factor(-100, "none", {"level": "warning"})
    with_critical = compute_crisis_factor(-100, "none", {"level": "critical"})
    assert no_draw < with_warning < with_critical


def test_coach_style_modifiers_have_expected_signs():
    aggressive = coach_style_modifiers("aggressive")
    solid = coach_style_modifiers("solid")
    creative = coach_style_modifiers("creative")
    # Aggressif tolere plus le risque (multiplier plus bas)
    assert aggressive["risk_mul"] < 0.50
    # Solide penalise plus le risque
    assert solid["risk_mul"] > 0.50
    # Creatif donne un bonus aux coups secondaires
    assert creative["creative_rank_bonus"] > 0
