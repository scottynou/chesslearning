import chess
from fastapi.testclient import TestClient

from app.main import app
from app.stockfish_engine import EngineLine
from app.strategy.opening_coach import list_available_plans
from app.strategy.phase_detector import detect_game_phase


class FakePlanStockfish:
    def analyze(self, fen: str, multipv: int, depth: int):
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
    assert data["planProgress"]["percent"] == 100


def test_opening_data_main_menu_is_pedagogical() -> None:
    plans = list_available_plans()
    assert len(plans) <= 14
    assert all(plan["tier"] != "hidden" for plan in plans)
    for plan in plans:
        assert plan["id"]
        assert plan["side"]
        assert plan["tier"]
        assert plan["difficulty"]
        assert plan["mainLineUci"]
        assert len(plan["coreIdeas"]) >= 3


def test_black_plan_menu_filters_after_e4() -> None:
    plans = list_available_plans(side="black", first_move="e2e4")
    plan_ids = {plan["id"] for plan in plans}
    assert "caro_kann_beginner" in plan_ids
    assert "black_e5_classical" in plan_ids
    assert "french_defense_beginner" in plan_ids
    assert "scandinavian_simple" in plan_ids
    assert "sicilian_dragon_simplified" in plan_ids
    assert "qgd_simplified" not in plan_ids


def test_black_plan_menu_filters_after_d4() -> None:
    plans = list_available_plans(side="black", first_move="d2d4")
    plan_ids = {plan["id"] for plan in plans}
    assert "qgd_simplified" in plan_ids
    assert "slav_beginner" in plan_ids
    assert "kings_indian_setup" in plan_ids
    assert "caro_kann_beginner" not in plan_ids


def test_phase_detector_detects_simple_endgame() -> None:
    fen = "8/8/8/8/8/8/4K3/6k1 w - - 0 1"
    assert detect_game_phase(fen, []) == "endgame"
