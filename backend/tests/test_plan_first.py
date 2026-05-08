import json
from types import SimpleNamespace

import chess
from fastapi.testclient import TestClient

from app.main import app
from app.stockfish_engine import EngineLine
from app.strategy.opening_coach import list_available_plans
from app.strategy.phase_detector import detect_game_phase


class FakePlanStockfish:
    def analyze(self, fen: str, multipv: int, depth: int, movetime_ms: int | None = None):
        board = chess.Board(fen)
        legal = {move.uci() for move in board.legal_moves}
        preferred = ["e2e4", "c7c6", "d2d4", "d7d5", "g1f3", "b8c6", "f1c4"]
        lines = []
        rank = 1
        for move in preferred:
            if move in legal:
                lines.append(EngineLine(rank, move, 40 - rank, None, [move]))
                rank += 1
        for move in board.legal_moves:
            if rank > multipv:
                break
            if move.uci() not in {line.move_uci for line in lines}:
                lines.append(EngineLine(rank, move.uci(), 5, None, [move.uci()]))
                rank += 1
        return lines


def test_caro_kann_after_e4_proposes_c6(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    board.push_uci("e2e4")
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "caro_kann_beginner",
            "elo": 1200,
            "moveHistoryUci": ["e2e4"],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["planState"]["status"] == "on_plan"
    assert data["planState"]["recommendedPlanMoves"] == ["c7c6"]
    assert data["mergedRecommendations"][0]["moveUci"] == "c7c6"
    assert len(data["mergedRecommendations"]) == 1
    assert data["phaseDisplay"]["key"] == "opening"
    assert data["phaseDisplay"]["maxVisibleMoves"] == 1
    assert data["expectedOpponentMove"] is None


def test_plan_recommendations_accepts_text_json_without_preflight(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    board.push_uci("e2e4")

    response = client.post(
        "/plan-recommendations",
        content=json.dumps(
            {
                "fen": board.fen(),
                "selectedPlanId": "caro_kann_beginner",
                "elo": 1200,
                "skillLevel": "beginner",
                "moveHistoryUci": ["e2e4"],
                "maxMoves": 5,
                "engineDepth": 1,
            }
        ),
        headers={
            "Origin": "https://chess-elo-coach-web-bh95.onrender.com",
            "Content-Type": "text/plain",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://chess-elo-coach-web-bh95.onrender.com"
    assert response.json()["primaryMove"]["moveUci"] == "c7c6"


def test_caro_kann_after_e4_c6_d4_proposes_d5(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    for move in ["e2e4", "c7c6", "d2d4"]:
        board.push_uci(move)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "caro_kann_beginner",
            "elo": 1200,
            "moveHistoryUci": ["e2e4", "c7c6", "d2d4"],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    assert response.json()["planState"]["recommendedPlanMoves"] == ["d7d5"]


def test_plan_status_after_opponent_deviation(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    for move in ["e2e4", "e7e5", "g1f3", "d7d6"]:
        board.push_uci(move)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "italian_game_beginner",
            "elo": 1200,
            "moveHistoryUci": ["e2e4", "e7e5", "g1f3", "d7d6"],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    assert response.json()["planState"]["status"] in {"opponent_deviated", "transposed"}


def test_opponent_deviation_on_opponent_turn_returns_expected_engine_move(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    moves = ["e2e4", "c7c5", "g1f3"]
    for move in moves:
        board.push_uci(move)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "italian_game_beginner",
            "elo": 1200,
            "moveHistoryUci": moves,
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["turnContext"]["opponentTurn"] is True
    assert data["primaryMove"] is None
    assert data["mergedRecommendations"] == []
    assert data["expectedOpponentMove"] is not None
    assert data["expectedOpponentMove"]["moveUci"] in {move.uci() for move in board.legal_moves}


def test_adaptive_signal_progressively_tracks_position_pressure() -> None:
    from app.strategy.plan_engine import adaptive_signal_for

    move = {"engineScore": 72, "tacticalRisk": 12, "warning": None}

    worse = adaptive_signal_for(
        primary_move=move,
        phase_status="opening_in_progress",
        blocked_expected_move=None,
        opening_state="on_track",
        player_turn=True,
        engine_candidates=[SimpleNamespace(eval_cp=-120, mate_in=None)],
    )
    critical = adaptive_signal_for(
        primary_move=move,
        phase_status="opening_in_progress",
        blocked_expected_move=None,
        opening_state="on_track",
        player_turn=True,
        engine_candidates=[SimpleNamespace(eval_cp=-320, mate_in=None)],
    )
    survival = adaptive_signal_for(
        primary_move=move,
        phase_status="opening_in_progress",
        blocked_expected_move=None,
        opening_state="on_track",
        player_turn=True,
        engine_candidates=[SimpleNamespace(eval_cp=-520, mate_in=None)],
    )
    stable = adaptive_signal_for(
        primary_move={**move, "engineScore": 82},
        phase_status="opening_in_progress",
        blocked_expected_move=None,
        opening_state="on_track",
        player_turn=True,
        engine_candidates=[SimpleNamespace(eval_cp=220, mate_in=None)],
    )
    comfortable = adaptive_signal_for(
        primary_move={**move, "engineScore": 90, "tacticalRisk": 4},
        phase_status="opening_in_progress",
        blocked_expected_move=None,
        opening_state="on_track",
        player_turn=True,
        engine_candidates=[SimpleNamespace(eval_cp=620, mate_in=None)],
    )

    assert worse["suggestedBoostDelta"] == 100
    assert critical["suggestedBoostDelta"] == 150
    assert survival["suggestedBoostDelta"] == 200
    assert stable["suggestedBoostDelta"] == 0
    assert comfortable["suggestedBoostDelta"] == -50


def test_adaptive_signal_ignores_candidate_quality_without_opponent_pressure() -> None:
    from app.strategy.plan_engine import adaptive_signal_for

    signal = adaptive_signal_for(
        primary_move={"engineScore": 24, "tacticalRisk": 80, "warning": "Coup difficile"},
        phase_status="opening_in_progress",
        blocked_expected_move=None,
        opening_state="on_track",
        player_turn=True,
        engine_candidates=[SimpleNamespace(eval_cp=120, mate_in=None)],
        draw_pressure={"level": "none"},
        opponent_strength={"level": "none", "suggestedBoostDelta": 0},
    )

    assert signal["pressure"] == "stable"
    assert signal["suggestedBoostDelta"] == 0


def test_human_accuracy_shaping_prefers_strong_human_band() -> None:
    from app.strategy.plan_engine import shape_recommendations_for_accuracy

    engine_perfect = {
        "moveUci": "d1h5",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 35,
        "engineScore": 100,
        "beginnerSimplicityScore": 48,
        "tacticalRisk": 18,
        "finalCoachScore": 82,
        "warning": None,
    }
    human_plan_move = {
        "moveUci": "g1f3",
        "source": "plan_and_engine",
        "engineRank": 3,
        "planFitScore": 92,
        "engineScore": 91,
        "beginnerSimplicityScore": 82,
        "tacticalRisk": 6,
        "finalCoachScore": 90,
        "warning": None,
    }
    weaker_move = {
        "moveUci": "b1a3",
        "source": "engine",
        "engineRank": 7,
        "planFitScore": 35,
        "engineScore": 64,
        "beginnerSimplicityScore": 58,
        "tacticalRisk": 22,
        "finalCoachScore": 56,
        "warning": None,
    }

    shaped = shape_recommendations_for_accuracy(
        [engine_perfect, human_plan_move, weaker_move],
        {"mode": "normal", "target": 92, "min": 90, "max": 94},
    )

    assert shaped[0]["moveUci"] == "g1f3"
    assert shaped[0]["accuracyBand"] == "normal"
    assert 90 <= shaped[0]["humanAccuracyEstimate"] <= 94


def test_strong_human_shaping_rejects_weak_plan_move() -> None:
    from app.strategy.plan_engine import shape_recommendations_for_accuracy

    engine_move = {
        "moveUci": "d1h5",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 35,
        "engineScore": 94,
        "beginnerSimplicityScore": 54,
        "tacticalRisk": 12,
        "finalCoachScore": 86,
        "warning": None,
    }
    weak_plan_move = {
        "moveUci": "g1f3",
        "source": "plan_and_engine",
        "engineRank": 6,
        "planFitScore": 96,
        "engineScore": 82,
        "beginnerSimplicityScore": 86,
        "tacticalRisk": 8,
        "finalCoachScore": 91,
        "warning": None,
    }

    shaped = shape_recommendations_for_accuracy(
        [weak_plan_move, engine_move],
        {"mode": "normal", "target": 92, "min": 90, "max": 94},
    )

    assert shaped[0]["moveUci"] == "d1h5"


def test_survival_accuracy_shaping_keeps_best_engine_move() -> None:
    from app.strategy.plan_engine import shape_recommendations_for_accuracy

    shaped = shape_recommendations_for_accuracy(
        [
            {
                "moveUci": "d1h5",
                "source": "engine",
                "engineRank": 1,
                "planFitScore": 35,
                "engineScore": 100,
                "beginnerSimplicityScore": 48,
                "tacticalRisk": 18,
                "finalCoachScore": 82,
                "warning": None,
            },
            {
                "moveUci": "g1f3",
                "source": "plan_and_engine",
                "engineRank": 3,
                "planFitScore": 92,
                "engineScore": 86,
                "beginnerSimplicityScore": 82,
                "tacticalRisk": 6,
                "finalCoachScore": 90,
                "warning": None,
            },
        ],
        {"mode": "survival", "target": 97, "min": 92, "max": 100},
    )

    assert shaped[0]["moveUci"] == "d1h5"


def test_drawish_positions_raise_hidden_accuracy_profile() -> None:
    from app.strategy.plan_engine import accuracy_profile_for

    board = chess.Board("8/8/8/2k5/8/2K5/4P3/8 w - - 0 42")
    profile = accuracy_profile_for(
        board=board,
        phase_display={"key": "endgame"},
        phase_status="opening_success",
        opening_state="completed",
        engine_candidates=[SimpleNamespace(eval_cp=18, mate_in=None)],
        move_history=["e2e4"] * 24,
        player_turn=True,
    )

    assert profile["mode"] == "draw_break"
    assert profile["target"] >= 91
    assert profile["drawPressure"]["level"] == "critical"


def test_elite_opponent_move_raises_accuracy_profile_immediately() -> None:
    from app.strategy.plan_engine import accuracy_profile_for

    profile = accuracy_profile_for(
        board=chess.Board(),
        phase_display={"key": "middlegame"},
        phase_status="opening_success",
        opening_state="completed",
        engine_candidates=[SimpleNamespace(eval_cp=60, mate_in=None)],
        move_history=["e2e4", "e7e5"],
        player_turn=True,
        opponent_strength={"level": "elite", "suggestedBoostDelta": 200},
        elo=1800,
    )

    assert profile["mode"] == "pressure"
    assert profile["target"] >= 96
    assert profile["min"] >= 92


def test_accuracy_profile_follows_selected_hidden_elo() -> None:
    from app.strategy.plan_engine import accuracy_profile_for

    common = {
        "board": chess.Board(),
        "phase_display": {"key": "middlegame"},
        "phase_status": "opening_success",
        "opening_state": "completed",
        "engine_candidates": [SimpleNamespace(eval_cp=60, mate_in=None)],
        "move_history": ["e2e4", "e7e5"],
        "player_turn": True,
        "opponent_strength": {"level": "none", "suggestedBoostDelta": 0},
    }

    assert accuracy_profile_for(**common, elo=1500)["target"] == 80
    assert accuracy_profile_for(**common, elo=2000)["target"] == 86
    assert accuracy_profile_for(**common, elo=3000)["target"] == 92


def test_planless_opening_fallback_stays_normal_until_real_pressure() -> None:
    from app.strategy.plan_engine import accuracy_profile_for

    profile = accuracy_profile_for(
        board=chess.Board(),
        phase_display={"key": "opening"},
        phase_status="fallback",
        opening_state="recoverable",
        engine_candidates=[SimpleNamespace(eval_cp=35, mate_in=None)],
        move_history=[],
        player_turn=True,
        opponent_strength={"level": "none", "suggestedBoostDelta": 0},
        elo=1500,
    )

    assert profile["mode"] == "normal"
    assert profile["target"] == 80


def test_accuracy_bands_are_distinct_for_three_player_profiles() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo

    assert accuracy_bands_for_elo(1500)["normal"] == {"target": 80, "min": 72, "max": 88, "planTolerance": 4}
    assert accuracy_bands_for_elo(2000)["normal"] == {"target": 86, "min": 80, "max": 93, "planTolerance": 3}
    assert accuracy_bands_for_elo(3000)["normal"] == {"target": 92, "min": 86, "max": 96, "planTolerance": 4}
    assert accuracy_bands_for_elo(3000)["elite_pressure"] == {"target": 97, "min": 94, "max": 100, "planTolerance": 0}
    assert accuracy_bands_for_elo(3000)["survival"] == {"target": 99, "min": 96, "max": 100, "planTolerance": 0}


def test_elite_profile_can_prefer_grandmaster_practical_move_over_perfect_engine_move() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    perfect_engine_move = {
        "moveUci": "d1a4",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 35,
        "engineScore": 100,
        "beginnerSimplicityScore": 55,
        "tacticalRisk": 8,
        "finalCoachScore": 90,
        "warning": None,
        "candidate": {"evalCp": 180},
    }
    grandmaster_practical_move = {
        "moveUci": "g1f3",
        "source": "engine",
        "engineRank": 5,
        "planFitScore": 78,
        "engineScore": 89,
        "beginnerSimplicityScore": 86,
        "tacticalRisk": 8,
        "finalCoachScore": 84,
        "warning": None,
        "candidate": {"evalCp": 92},
    }

    shaped = shape_recommendations_for_accuracy(
        [perfect_engine_move, grandmaster_practical_move],
        {"mode": "normal", "targetElo": 3000, "humanSeed": 123, **accuracy_bands_for_elo(3000)["normal"]},
    )

    assert shaped[0]["moveUci"] == "g1f3"
    assert shaped[0]["humanAccuracyEstimate"] < 94


def test_elite_profile_keeps_best_move_when_survival_is_required() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    best_engine_move = {
        "moveUci": "d1h5",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 35,
        "engineScore": 100,
        "beginnerSimplicityScore": 48,
        "tacticalRisk": 38,
        "finalCoachScore": 96,
        "warning": None,
        "candidate": {"evalCp": -320},
    }
    human_looking_move = {
        "moveUci": "g1f3",
        "source": "engine",
        "engineRank": 3,
        "planFitScore": 82,
        "engineScore": 96,
        "beginnerSimplicityScore": 88,
        "tacticalRisk": 8,
        "finalCoachScore": 89,
        "warning": None,
        "candidate": {"evalCp": -480},
    }

    shaped = shape_recommendations_for_accuracy(
        [human_looking_move, best_engine_move],
        {"mode": "survival", "targetElo": 3000, "humanSeed": 123, **accuracy_bands_for_elo(3000)["survival"]},
    )

    assert shaped[0]["moveUci"] == "d1h5"


def test_elite_profile_rejects_unsafe_or_below_threshold_practical_move() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    perfect_engine_move = {
        "moveUci": "d1a4",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 35,
        "engineScore": 100,
        "beginnerSimplicityScore": 55,
        "tacticalRisk": 8,
        "finalCoachScore": 90,
        "warning": None,
        "candidate": {"evalCp": 180},
    }
    risky_human_move = {
        "moveUci": "f3g5",
        "source": "engine",
        "engineRank": 3,
        "planFitScore": 82,
        "engineScore": 92,
        "beginnerSimplicityScore": 84,
        "tacticalRisk": 46,
        "finalCoachScore": 88,
        "warning": None,
        "candidate": {"evalCp": 118},
    }
    safe_practical_move = {
        "moveUci": "g1f3",
        "source": "engine",
        "engineRank": 4,
        "planFitScore": 78,
        "engineScore": 88,
        "beginnerSimplicityScore": 82,
        "tacticalRisk": 10,
        "finalCoachScore": 84,
        "warning": None,
        "candidate": {"evalCp": 86},
    }
    below_threshold_move = {
        "moveUci": "b1c3",
        "source": "plan_and_engine",
        "engineRank": 5,
        "planFitScore": 94,
        "engineScore": 84,
        "beginnerSimplicityScore": 90,
        "tacticalRisk": 6,
        "finalCoachScore": 86,
        "warning": None,
        "candidate": {"evalCp": 54},
    }

    shaped = shape_recommendations_for_accuracy(
        [perfect_engine_move, risky_human_move, safe_practical_move, below_threshold_move],
        {"mode": "normal", "targetElo": 3000, "humanSeed": 123, **accuracy_bands_for_elo(3000)["normal"]},
    )

    assert shaped[0]["moveUci"] == "g1f3"
    assert shaped[1]["moveUci"] != "f3g5"
    assert shaped[0]["moveUci"] != "b1c3"


def test_elite_humanization_is_deterministic_for_same_seed() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    items = [
        {
            "moveUci": "d1a4",
            "source": "engine",
            "engineRank": 1,
            "planFitScore": 35,
            "engineScore": 100,
            "beginnerSimplicityScore": 55,
            "tacticalRisk": 8,
            "finalCoachScore": 90,
            "warning": None,
            "candidate": {"evalCp": 180},
        },
        {
            "moveUci": "g1f3",
            "source": "engine",
            "engineRank": 3,
            "planFitScore": 80,
            "engineScore": 91,
            "beginnerSimplicityScore": 84,
            "tacticalRisk": 10,
            "finalCoachScore": 86,
            "warning": None,
            "candidate": {"evalCp": 108},
        },
    ]
    profile = {"mode": "normal", "targetElo": 3000, "humanSeed": 98765, **accuracy_bands_for_elo(3000)["normal"]}

    first = shape_recommendations_for_accuracy(items, profile)
    second = shape_recommendations_for_accuracy(items, profile)

    assert [item["moveUci"] for item in first] == [item["moveUci"] for item in second]


def test_solid_1500_profile_rejects_unnecessary_tactical_risk() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    tactical_move = {
        "moveUci": "d1h5",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 35,
        "engineScore": 88,
        "beginnerSimplicityScore": 50,
        "tacticalRisk": 50,
        "finalCoachScore": 82,
        "warning": None,
        "candidate": {"evalCp": 120},
    }
    healthy_move = {
        "moveUci": "g1f3",
        "source": "engine",
        "engineRank": 3,
        "planFitScore": 35,
        "engineScore": 84,
        "beginnerSimplicityScore": 82,
        "tacticalRisk": 10,
        "finalCoachScore": 80,
        "warning": None,
        "candidate": {"evalCp": 92},
    }

    shaped = shape_recommendations_for_accuracy(
        [tactical_move, healthy_move],
        {"mode": "normal", **accuracy_bands_for_elo(1500)["normal"]},
    )

    assert shaped[0]["moveUci"] == "g1f3"


def test_solid_1500_opening_safety_rejects_early_rook_pawn_push() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    early_flank_push = {
        "moveUci": "h2h4",
        "source": "engine",
        "engineRank": 15,
        "planFitScore": 35,
        "engineScore": 92,
        "beginnerSimplicityScore": 58,
        "tacticalRisk": 13,
        "finalCoachScore": 84,
        "warning": None,
        "candidate": {"evalCp": 40},
    }
    central_move = {
        "moveUci": "e2e4",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 35,
        "engineScore": 86,
        "beginnerSimplicityScore": 76,
        "tacticalRisk": 12,
        "finalCoachScore": 78,
        "warning": None,
        "candidate": {"evalCp": 30},
    }

    shaped = shape_recommendations_for_accuracy(
        [early_flank_push, central_move],
        {
            "mode": "normal",
            "targetElo": 1500,
            "fen": chess.STARTING_FEN,
            "openingSafetyMode": True,
            **accuracy_bands_for_elo(1500)["normal"],
        },
    )

    assert shaped[0]["moveUci"] == "e2e4"


def test_strong_2000_opening_safety_rejects_knight_to_rim() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    board = chess.Board()
    for move in ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"]:
        board.push_uci(move)
    rim_knight = {
        "moveUci": "b1a3",
        "source": "engine",
        "engineRank": 15,
        "planFitScore": 35,
        "engineScore": 92,
        "beginnerSimplicityScore": 66,
        "tacticalRisk": 13,
        "finalCoachScore": 84,
        "warning": None,
        "candidate": {"evalCp": 42},
    }
    natural_development = {
        "moveUci": "b1c3",
        "source": "engine",
        "engineRank": 4,
        "planFitScore": 35,
        "engineScore": 90,
        "beginnerSimplicityScore": 76,
        "tacticalRisk": 14,
        "finalCoachScore": 82,
        "warning": None,
        "candidate": {"evalCp": 34},
    }

    shaped = shape_recommendations_for_accuracy(
        [rim_knight, natural_development],
        {
            "mode": "normal",
            "targetElo": 2000,
            "fen": board.fen(),
            "openingSafetyMode": True,
            **accuracy_bands_for_elo(2000)["normal"],
        },
    )

    assert shaped[0]["moveUci"] == "b1c3"


def test_elite_3000_opening_safety_prefers_human_central_play_over_flank_noise() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    early_flank_push = {
        "moveUci": "h2h4",
        "source": "engine",
        "engineRank": 8,
        "planFitScore": 35,
        "engineScore": 92,
        "beginnerSimplicityScore": 58,
        "tacticalRisk": 13,
        "finalCoachScore": 86,
        "warning": None,
        "candidate": {"evalCp": 60},
    }
    central_gm_move = {
        "moveUci": "d2d4",
        "source": "engine",
        "engineRank": 2,
        "planFitScore": 35,
        "engineScore": 98,
        "beginnerSimplicityScore": 64,
        "tacticalRisk": 23,
        "finalCoachScore": 88,
        "warning": None,
        "candidate": {"evalCp": 90},
    }

    shaped = shape_recommendations_for_accuracy(
        [early_flank_push, central_gm_move],
        {
            "mode": "normal",
            "targetElo": 3000,
            "humanSeed": 123,
            "fen": chess.STARTING_FEN,
            "openingSafetyMode": True,
            **accuracy_bands_for_elo(3000)["normal"],
        },
    )

    assert shaped[0]["moveUci"] == "d2d4"


def test_elite_engine_search_profile_uses_large_free_local_multipv() -> None:
    from app.strategy.plan_engine import engine_search_profile_for_elo

    profile = engine_search_profile_for_elo(3000, {"technical_limit": 5})

    assert profile["selectionMode"] == "elite_human_practical"
    assert profile["multipv"] == 30
    assert profile["minDepth"] >= 14


def test_rank_candidates_keeps_3200_as_pure_stockfish_order() -> None:
    from app.elo_ranker import rank_candidates

    candidates = rank_candidates(
        chess.STARTING_FEN,
        [
            EngineLine(2, "d2d4", 80, None, ["d2d4", "d7d5"]),
            EngineLine(1, "g1f3", 60, None, ["g1f3", "g8f6"]),
        ],
        elo=3200,
        max_moves=2,
    )

    assert candidates[0].move_uci == "g1f3"
    assert candidates[0].stockfish_rank == 1


def test_elite_plan_recommendations_expose_local_humanization_details(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": chess.STARTING_FEN,
            "selectedPlanId": None,
            "userSide": "white",
            "elo": 3000,
            "moveHistoryUci": [],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["technicalDetails"]["selectionMode"] == "elite_human_practical"
    assert data["technicalDetails"]["humanizationMode"] == "gm_practical"
    assert isinstance(data["technicalDetails"]["humanSeed"], int)
    assert data["aiRerankStatus"]["fallbackReason"] == "elite_humanization_local_only"


def test_ai_rerank_prompt_uses_strong_human_profile_without_1200() -> None:
    from app.ai_reranker import _prompt

    payload = json.loads(
        _prompt(
            fen=chess.STARTING_FEN,
            selected_plan={"id": "italian_game_beginner", "nameFr": "Partie italienne", "side": "white", "coreIdeas": []},
            phase="middlegame",
            opening_state="completed",
            move_history=["e2e4", "e7e5"],
            recommendations=[
                {
                    "moveUci": "g1f3",
                    "engineScore": 93,
                    "planFitScore": 90,
                    "tacticalRisk": 8,
                    "humanAccuracyEstimate": 93,
                    "accuracyBand": "normal",
                }
            ],
            strong_human_profile={"mode": "normal", "targetMin": 90, "targetMax": 94},
        )
    )

    assert "1200" not in payload["task"]
    assert payload["strongHumanProfile"]["targetMin"] == 90


def test_flat_middlegame_raises_draw_pressure_early() -> None:
    from app.strategy.plan_engine import draw_pressure_for

    board = chess.Board()
    moves = ["e2e4", "e7e5", "g1f3", "g8f6", "f1e2", "f8e7", "e1g1", "e8g8", "d2d3", "d7d6"]
    for move in moves:
        board.push_uci(move)

    pressure = draw_pressure_for(
        board=board,
        phase_display={"key": "middlegame"},
        move_history=moves,
        engine_candidates=[
            SimpleNamespace(eval_cp=18, mate_in=None),
            SimpleNamespace(eval_cp=28, mate_in=None),
            SimpleNamespace(eval_cp=37, mate_in=None),
        ],
    )

    assert pressure["level"] == "warning"
    assert "plate" in pressure["reason"].lower() or "nulle" in pressure["reason"].lower()


def test_drawish_adaptive_signal_boosts_precision() -> None:
    from app.strategy.plan_engine import adaptive_signal_for

    signal = adaptive_signal_for(
        primary_move={"engineScore": 88, "tacticalRisk": 12, "warning": None},
        phase_status="opening_success",
        blocked_expected_move=None,
        opening_state="completed",
        player_turn=True,
        engine_candidates=[SimpleNamespace(eval_cp=12, mate_in=None)],
        draw_pressure={"level": "critical"},
    )

    assert signal["pressure"] == "drawish"
    assert signal["suggestedBoostDelta"] == 200


def test_opponent_engine_quality_raises_adaptive_signal() -> None:
    from app.strategy.plan_engine import adaptive_signal_for, opponent_move_strength_from_lines

    strength = opponent_move_strength_from_lines(
        "e7e5",
        [
            SimpleNamespace(stockfish_rank=1, move_uci="e7e5", eval_cp=34, mate_in=None),
            SimpleNamespace(stockfish_rank=2, move_uci="c7c5", eval_cp=18, mate_in=None),
        ],
    )
    signal = adaptive_signal_for(
        primary_move={"engineScore": 88, "tacticalRisk": 8, "warning": None},
        phase_status="opening_in_progress",
        blocked_expected_move=None,
        opening_state="on_track",
        player_turn=True,
        engine_candidates=[SimpleNamespace(eval_cp=60, mate_in=None)],
        draw_pressure={"level": "none"},
        opponent_strength=strength,
    )

    assert strength["level"] == "elite"
    assert signal["pressure"] == "worse"
    assert signal["suggestedBoostDelta"] == 200


def test_draw_break_shaping_prefers_winning_chances_over_flat_move() -> None:
    from app.strategy.plan_engine import shape_recommendations_for_accuracy

    flat_move = {
        "moveUci": "c3d3",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 35,
        "engineScore": 92,
        "beginnerSimplicityScore": 76,
        "tacticalRisk": 8,
        "finalCoachScore": 86,
        "warning": None,
        "candidate": {"evalCp": 12},
    }
    active_move = {
        "moveUci": "e2e4",
        "source": "engine",
        "engineRank": 2,
        "planFitScore": 35,
        "engineScore": 90,
        "beginnerSimplicityScore": 72,
        "tacticalRisk": 14,
        "finalCoachScore": 84,
        "warning": None,
        "candidate": {"evalCp": 120},
    }

    shaped = shape_recommendations_for_accuracy(
        [flat_move, active_move],
        {"mode": "draw_break", "target": 94, "min": 88, "max": 99, "drawPressure": {"level": "critical"}},
    )

    assert shaped[0]["moveUci"] == "e2e4"
    assert shaped[0]["accuracyBand"] == "draw_break"


def test_normal_accuracy_shaping_avoids_unnecessary_perfection() -> None:
    from app.strategy.plan_engine import accuracy_bands_for_elo, shape_recommendations_for_accuracy

    perfect_move = {
        "moveUci": "d1a4",
        "source": "engine",
        "engineRank": 1,
        "planFitScore": 42,
        "engineScore": 96,
        "beginnerSimplicityScore": 58,
        "tacticalRisk": 8,
        "finalCoachScore": 90,
        "warning": None,
        "candidate": {"evalCp": 140},
    }
    practical_move = {
        "moveUci": "g1f3",
        "source": "engine",
        "engineRank": 3,
        "planFitScore": 58,
        "engineScore": 78,
        "beginnerSimplicityScore": 82,
        "tacticalRisk": 10,
        "finalCoachScore": 82,
        "warning": None,
        "candidate": {"evalCp": 88},
    }

    shaped = shape_recommendations_for_accuracy(
        [perfect_move, practical_move],
        {"mode": "normal", **accuracy_bands_for_elo(1600)["normal"]},
    )

    assert shaped[0]["moveUci"] == "g1f3"
    assert shaped[0]["humanAccuracyEstimate"] < 90


def test_player_turn_after_deviation_returns_primary_move(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    moves = ["e2e4", "c7c5"]
    for move in moves:
        board.push_uci(move)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "italian_game_beginner",
            "elo": 1200,
            "moveHistoryUci": moves,
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["turnContext"]["playerTurn"] is True
    assert data["primaryMove"] is not None
    assert data["expectedOpponentMove"] is None
    assert data["primaryMove"]["moveUci"] in {move.uci() for move in board.legal_moves}


def test_game_over_does_not_force_recommendation(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    moves = ["f2f3", "e7e5", "g2g4", "d8h4"]
    for move in moves:
        board.push_uci(move)
    assert board.is_checkmate()
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "italian_game_beginner",
            "elo": 1200,
            "moveHistoryUci": moves,
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["turnContext"]["gameOver"] is True
    assert data["primaryMove"] is None
    assert data["expectedOpponentMove"] is None


def test_selected_plan_stays_locked_when_position_matches_another_plan(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    for move in ["e2e4", "c7c6", "d2d4"]:
        board.push_uci(move)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "italian_game_beginner",
            "elo": 1200,
            "moveHistoryUci": ["e2e4", "c7c6", "d2d4"],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["selectedPlan"]["id"] == "italian_game_beginner"
    assert data["planState"]["selectedPlanId"] == "italian_game_beginner"
    assert data["planState"]["status"] == "opponent_deviated"


def test_opponent_turn_returns_expected_move_without_recommendation(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    for move in ["e2e4", "c7c6"]:
        board.push_uci(move)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "caro_kann_beginner",
            "elo": 1200,
            "moveHistoryUci": ["e2e4", "c7c6"],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["primaryMove"] is None
    assert data["planMoves"] == []
    assert data["planState"]["recommendedPlanMoves"] == []
    assert data["recommendedPlanMoves"] == []
    assert data["expectedOpponentMove"]["moveUci"] == "d2d4"


def test_free_imported_position_uses_user_side_for_turn_context(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    board.push_uci("e2e4")
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": None,
            "userSide": "white",
            "elo": 1200,
            "moveHistoryUci": [],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["turnContext"]["playerTurn"] is False
    assert data["turnContext"]["opponentTurn"] is True
    assert data["expectedOpponentMove"] is not None
    assert data["mergedRecommendations"] == []


def test_skill_level_changes_visible_technical_window(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    board.push_uci("e2e4")
    base = {
        "fen": board.fen(),
        "selectedPlanId": "caro_kann_beginner",
        "elo": 1200,
        "moveHistoryUci": ["e2e4"],
        "maxMoves": 10,
        "engineDepth": 1,
    }
    beginner = client.post("/plan-recommendations", json={**base, "skillLevel": "beginner"}).json()
    pro = client.post("/plan-recommendations", json={**base, "skillLevel": "pro", "elo": 2800}).json()
    assert len(beginner["technicalEngineMoves"]) <= 5
    assert len(pro["technicalEngineMoves"]) >= len(beginner["technicalEngineMoves"])


def test_opening_success_after_main_line(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    board = chess.Board()
    for move in ["e2e4", "c7c6", "d2d4", "d7d5"]:
        board.push_uci(move)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "caro_kann_beginner",
            "elo": 1200,
            "skillLevel": "beginner",
            "moveHistoryUci": ["e2e4", "c7c6", "d2d4", "d7d5"],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["phaseStatus"] == "opening_success"
    assert data["phaseDisplay"]["key"] == "middlegame"
    assert data["planProgress"]["percent"] == 100


def test_completed_opening_keeps_single_visible_choice(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    moves = ["e2e4", "c7c6", "d2d4", "d7d5", "b1c3", "d5e4", "c3e4", "g8f6", "e4f6", "e7f6", "g1f3"]
    board = chess.Board()
    for move in moves:
        board.push_uci(move)
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "caro_kann_beginner",
            "elo": 1800,
            "skillLevel": "intermediate",
            "moveHistoryUci": moves,
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["phaseDisplay"]["key"] == "middlegame"
    assert data["phaseDisplay"]["recommendationStyle"] == "single"
    assert data["phaseDisplay"]["maxVisibleMoves"] == 1
    assert len(data["mergedRecommendations"]) == 1
    assert data["mergedRecommendations"][0]["displayRole"] == "Coup recommande"
    assert data["mergedRecommendations"][0]["arrowColor"] == "rgba(224,185,118,0.78)"


def test_simple_endgame_uses_conversion_display(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    fen = "8/8/8/8/8/8/4K3/6k1 w - - 0 1"
    response = client.post(
        "/plan-recommendations",
        json={
            "fen": fen,
            "selectedPlanId": None,
            "elo": 1800,
            "skillLevel": "intermediate",
            "moveHistoryUci": [],
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )
    data = response.json()
    assert data["phaseDisplay"]["key"] == "endgame"
    assert data["phaseDisplay"]["recommendationStyle"] == "single"
    assert data["phaseDisplay"]["maxVisibleMoves"] == 1
    assert len(data["mergedRecommendations"]) <= 1


def test_opening_data_main_menu_is_pedagogical() -> None:
    plans = list_available_plans()
    assert 32 <= len(plans) <= 40
    assert all(plan["tier"] != "hidden" for plan in plans)
    for plan in plans:
        assert plan["id"]
        assert plan["side"]
        assert plan["tier"]
        assert plan["difficulty"]
        assert plan["mainLineUci"]
        assert len(plan["coreIdeas"]) >= 3
        assert len(plan["shortHistory"]) > 70
    assert len({plan["shortHistory"] for plan in plans}) == len(plans)


def test_white_repertoire_has_multiple_difficulty_levels() -> None:
    plans = list_available_plans(side="white")
    plan_ids = {plan["id"] for plan in plans}
    assert {"italian_game_beginner", "london_system_beginner", "english_opening_practical", "catalan_simplified"} <= plan_ids
    assert {plan["difficulty"] for plan in plans} >= {"easy", "medium", "hard"}


def test_black_plan_menu_filters_after_e4() -> None:
    plans = list_available_plans(side="black", first_move="e2e4")
    plan_ids = {plan["id"] for plan in plans}
    assert "caro_kann_beginner" in plan_ids
    assert "black_e5_classical" in plan_ids
    assert "french_defense_beginner" in plan_ids
    assert "scandinavian_simple" in plan_ids
    assert "sicilian_dragon_simplified" in plan_ids
    assert "pirc_defense_learning" in plan_ids
    assert "alekhine_defense_learning" in plan_ids
    assert "qgd_simplified" not in plan_ids
    assert "black_flexible_d5_classical" not in plan_ids


def test_black_plan_menu_filters_after_d4() -> None:
    plans = list_available_plans(side="black", first_move="d2d4")
    plan_ids = {plan["id"] for plan in plans}
    assert "qgd_simplified" in plan_ids
    assert "slav_beginner" in plan_ids
    assert "kings_indian_setup" in plan_ids
    assert "nimzo_indian_simplified" in plan_ids
    assert "grunfeld_simplified" in plan_ids
    assert "caro_kann_beginner" not in plan_ids


def test_black_plan_menu_filters_after_flexible_first_moves() -> None:
    after_nf3 = {plan["id"] for plan in list_available_plans(side="black", first_move="g1f3")}
    assert "black_flexible_d5_classical" in after_nf3
    assert "black_fianchetto_universal" in after_nf3
    assert "caro_kann_beginner" not in after_nf3

    after_c4 = {plan["id"] for plan in list_available_plans(side="black", first_move="c2c4")}
    assert "english_e5_response" in after_c4
    assert "symmetrical_english_response" in after_c4
    assert "caro_kann_beginner" not in after_c4


def test_phase_detector_detects_simple_endgame() -> None:
    fen = "8/8/8/8/8/8/4K3/6k1 w - - 0 1"
    assert detect_game_phase(fen, []) == "endgame"


def test_phase_detector_does_not_treat_early_queen_trade_as_endgame() -> None:
    moves = ["e2e4", "e7e5", "d1h5", "b8c6", "h5e5", "c6e5"]
    board = chess.Board()
    for move in moves:
        board.push_uci(move)

    assert detect_game_phase(board.fen(), moves) == "opening"


def test_opening_deviation_can_be_abandoned_and_create_event(monkeypatch) -> None:
    import app.strategy.plan_engine as plan_engine

    monkeypatch.setattr(plan_engine, "StockfishEngine", lambda: FakePlanStockfish())
    client = TestClient(app)
    moves = ["e2e4", "c7c5", "g1f3", "d7d6", "f1c4", "g8f6"]
    board = chess.Board()
    for move in moves:
        board.push_uci(move)

    response = client.post(
        "/plan-recommendations",
        json={
            "fen": board.fen(),
            "selectedPlanId": "italian_game_beginner",
            "elo": 1200,
            "skillLevel": "beginner",
            "moveHistoryUci": moves,
            "maxMoves": 5,
            "engineDepth": 1,
        },
    )

    data = response.json()
    assert response.status_code == 200
    assert data["openingState"] in {"recoverable", "abandoned"}
    assert data["strategicPlan"]["title"]
    if data["openingState"] == "abandoned":
        assert data["phaseDisplay"]["key"] == "middlegame"
        assert data["planEvent"]["title"] == "Plan initial abandonne"


def test_live_plan_insight_returns_heuristic_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "heuristic")
    client = TestClient(app)
    board = chess.Board()
    response = client.post(
        "/live-plan-insight",
        json={
            "fen": board.fen(),
            "selectedPlanId": "italian_game_beginner",
            "moveHistoryUci": [],
            "phase": "opening",
            "openingState": "on_track",
            "strategicPlan": {
                "title": "Partie italienne",
                "goal": "Developper vite et viser le centre.",
                "reason": "Le plan est encore coherent.",
                "nextObjective": "Jouer un coup simple de developpement.",
            },
            "primaryMove": None,
            "expectedOpponentMove": None,
            "planEvent": None,
        },
    )

    data = response.json()
    assert response.status_code == 200
    assert data["analysisProvider"] == "heuristic"
    assert data["analysisKind"] == "heuristic"
    assert data["headline"]
    assert data["currentPlan"]
