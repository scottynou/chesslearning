import re

import chess
from fastapi.testclient import TestClient

from app.beginner_notation import beginner_notation_for_uci
from app.evaluation_label import evaluation_label
from app.explanation_quality import validate_beginner_explanation
from app.main import app
from app.pv_translator import translate_pv
from app.stockfish_engine import EngineLine


def test_beginner_notation_converts_knight_move() -> None:
    fen = "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1"
    notation = beginner_notation_for_uci(fen, "g8f6", "Nf6")
    assert notation.beginner_label == "♞ Cavalier g8 → f6"
    assert notation.french_san == "Cf6"


def test_evaluation_label_for_small_black_advantage() -> None:
    assert evaluation_label(-31) == "Léger avantage noir"
    assert evaluation_label(24) == "Position équilibrée"
    assert evaluation_label(145) == "Avantage clair blanc"
    assert evaluation_label(-320) == "Avantage décisif noir"


def test_pv_translator_does_not_return_raw_uci_sequence() -> None:
    fen = "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1"
    translated = translate_pv(fen, ["g8f6", "e2e3", "c7c5"])
    text = " ".join(item["simpleExplanation"] for item in translated)
    assert not re.search(r"\b[a-h][1-8][a-h][1-8](?:\s+[a-h][1-8][a-h][1-8])+\b", text)


def test_explanation_quality_rejects_raw_uci_sequence() -> None:
    errors = validate_beginner_explanation("g8f6 e2e3 c7c5", "Cavalier")
    assert "contains_raw_uci_sequence" in errors


def test_explanation_quality_rejects_text_without_piece_or_square() -> None:
    errors = validate_beginner_explanation("Continue le développement et améliore la position.", "Cavalier")
    assert "contains_no_square" in errors
    assert "missing_played_piece_name" in errors


class FakeStockfishEngine:
    def analyze(self, fen: str, multipv: int, depth: int):
        board = chess.Board(fen)
        if multipv == 1:
            return [EngineLine(1, next(iter(board.legal_moves)).uci(), -60, None, [next(iter(board.legal_moves)).uci()])]
        return [
            EngineLine(1, "e2e4", 45, None, ["e2e4", "e7e5"]),
            EngineLine(2, "d2d4", 30, None, ["d2d4", "d7d5"]),
            EngineLine(3, "g1f3", 15, None, ["g1f3", "d7d5"]),
        ]


def test_review_move_works_when_played_move_is_not_top_10(monkeypatch) -> None:
    import app.review_service as review_service

    monkeypatch.setattr(review_service, "StockfishEngine", lambda: FakeStockfishEngine())
    client = TestClient(app)
    before = chess.STARTING_FEN
    board = chess.Board(before)
    board.push_uci("h2h4")

    response = client.post(
        "/review-move",
        json={
            "fenBefore": before,
            "fenAfter": board.fen(),
            "moveUci": "h2h4",
            "elo": 1200,
        },
    )

    assert response.status_code == 200
    assert response.json()["moveLabel"] == "♙ Pion h2 → h4"
    assert response.json()["bestMoveWasDifferent"] is True


def test_bot_move_returns_legal_move_and_respects_elo_pool(monkeypatch) -> None:
    import app.bot_service as bot_service

    monkeypatch.setattr(bot_service, "StockfishEngine", lambda: FakeStockfishEngine())
    client = TestClient(app)
    response = client.post(
        "/bot-move",
        json={
            "fen": chess.STARTING_FEN,
            "elo": 3200,
            "maxMoves": 10,
            "engineDepth": 1,
            "botStyle": "balanced",
        },
    )

    assert response.status_code == 200
    move_uci = response.json()["move"]["moveUci"]
    assert chess.Move.from_uci(move_uci) in chess.Board(chess.STARTING_FEN).legal_moves
    assert move_uci in {"e2e4", "d2d4"}
