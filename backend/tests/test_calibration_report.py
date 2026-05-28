from fastapi.testclient import TestClient
from types import SimpleNamespace

import chess

from app.main import app
from app.strategy.plan_engine import position_win_rate_for, shape_recommendations_for_accuracy
from app.strategy.scoring_profile import accuracy_bands_for_profile


def test_calibration_report_exposes_profile_style_matrix() -> None:
    client = TestClient(app)
    response = client.get("/calibration-report")

    assert response.status_code == 200
    data = response.json()
    assert data["opponentElo"] == 1600
    assert data["sampleCount"] >= 3
    assert len(data["rows"]) == 20
    assert set(data["bestByProfile"]) == {"beginner", "lambda", "strong", "veryStrong"}

    beginner_balanced = next(row for row in data["rows"] if row["profile"] == "beginner" and row["style"] == "balanced")
    assert beginner_balanced["targetAccuracy"] == 72

    lambda_balanced = next(row for row in data["rows"] if row["profile"] == "lambda" and row["style"] == "balanced")
    assert lambda_balanced["targetAccuracy"] == 79
    assert 0 <= lambda_balanced["humanizationScore"] <= 100
    assert 5 <= lambda_balanced["winRateVsOpponent"] <= 96


def test_recommendation_annotation_adds_winrate_and_humanization() -> None:
    shaped = shape_recommendations_for_accuracy(
        [
            {
                "moveUci": "d1a4",
                "source": "engine",
                "engineRank": 1,
                "planFitScore": 42,
                "engineScore": 100,
                "beginnerSimplicityScore": 58,
                "tacticalRisk": 8,
                "finalCoachScore": 90,
                "warning": None,
                "candidate": {"evalCp": 180, "mateIn": None},
            },
            {
                "moveUci": "g1f3",
                "source": "engine",
                "engineRank": 3,
                "planFitScore": 58,
                "engineScore": 82,
                "beginnerSimplicityScore": 82,
                "tacticalRisk": 10,
                "finalCoachScore": 82,
                "warning": None,
                "candidate": {"evalCp": 88, "mateIn": None},
            },
        ],
        {"mode": "normal", "humanProfile": "lambda", **accuracy_bands_for_profile("lambda", 1500)["normal"]},
    )

    assert "winRateEstimate" in shaped[0]
    assert "humanizationScore" in shaped[0]
    assert 0 <= shaped[0]["humanizationScore"] <= 100
    assert 0 <= shaped[0]["winRateEstimate"] <= 100


def test_position_win_rate_is_reported_from_player_side() -> None:
    board = chess.Board()
    board.push_uci("e2e4")

    rate = position_win_rate_for(
        board=board,
        engine_candidates=[SimpleNamespace(stockfish_rank=1, eval_cp=120, mate_in=None)],
        user_side="white",
    )

    assert rate["playerSide"] == "white"
    assert rate["perspective"] == "player"
    assert rate["blackWinPercent"] > 50
    assert rate["playerWinPercent"] == rate["whiteWinPercent"]
    assert rate["playerWinPercent"] < 50


def test_position_win_rate_prefers_stockfish_wdl() -> None:
    board = chess.Board()
    board.push_uci("e2e4")

    rate = position_win_rate_for(
        board=board,
        engine_candidates=[SimpleNamespace(stockfish_rank=1, eval_cp=0, mate_in=None, wdl=[650, 300, 50])],
        user_side="black",
    )

    assert rate["source"] == "stockfish_wdl"
    assert rate["sideToMoveWdl"] == [650, 300, 50]
    assert rate["blackWinPercent"] == 65.0
    assert rate["playerWinPercent"] == 65.0
