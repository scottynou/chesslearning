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
        engine_candidates=[SimpleNamespace(eval_cp=360, mate_in=None)],
    )

    assert worse["suggestedBoostDelta"] == 50
    assert critical["suggestedBoostDelta"] == 150
    assert survival["suggestedBoostDelta"] == 200
    assert stable["suggestedBoostDelta"] == -50
    assert comfortable["suggestedBoostDelta"] == -100


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
        "engineScore": 86,
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
        {"mode": "human", "target": 84, "min": 78, "max": 89},
    )

    assert shaped[0]["moveUci"] == "g1f3"
    assert shaped[0]["accuracyBand"] == "human"
    assert shaped[0]["humanAccuracyEstimate"] <= 89


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
    assert signal["suggestedBoostDelta"] == 100


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


def test_completed_opening_switches_to_middlegame_ranked_choices(monkeypatch) -> None:
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
    assert data["phaseDisplay"]["recommendationStyle"] == "ranked"
    assert 1 <= len(data["mergedRecommendations"]) <= 3
    assert data["mergedRecommendations"][0]["displayRole"] == "Meilleur"


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
    assert data["phaseDisplay"]["recommendationStyle"] == "conversion"
    assert len(data["mergedRecommendations"]) <= 2


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
