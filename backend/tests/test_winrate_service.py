from __future__ import annotations

import sqlite3

import chess
from fastapi.testclient import TestClient

from app.main import app
from app.stockfish_engine import EngineLine
from app.winrate_service import get_winrate, normalize_fen_for_stats


def test_normalized_fen_ignores_counters() -> None:
    early = normalize_fen_for_stats("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    late = normalize_fen_for_stats("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 17 42")

    assert early == late


def test_lichess_exact_uses_draws_in_total(tmp_path) -> None:
    db_path = tmp_path / "winrates.sqlite"
    board = chess.Board()
    create_stats_db(db_path)
    insert_stats(
        db_path,
        fen_key=normalize_fen_for_stats(board),
        speed="blitz",
        rating_bucket=1400,
        white_wins=40,
        draws=30,
        black_wins=30,
    )

    white = get_winrate(
        fen=board.fen(),
        perspective="white",
        player_rating=1400,
        opponent_rating=1400,
        speed="blitz",
        db_path=db_path,
        allow_stockfish=False,
    )
    black = get_winrate(
        fen=board.fen(),
        perspective="black",
        player_rating=1400,
        opponent_rating=1400,
        speed="blitz",
        db_path=db_path,
        allow_stockfish=False,
    )

    assert white.source == "lichess_exact"
    assert white.confidence == "medium"
    assert white.winrate == 40.0
    assert black.winrate == 30.0


def test_side_to_move_perspective_uses_position_turn(tmp_path) -> None:
    db_path = tmp_path / "winrates.sqlite"
    board = chess.Board()
    board.push_uci("e2e4")
    create_stats_db(db_path)
    insert_stats(
        db_path,
        fen_key=normalize_fen_for_stats(board),
        speed="rapid",
        rating_bucket=1600,
        white_wins=35,
        draws=20,
        black_wins=45,
    )

    result = get_winrate(
        fen=board.fen(),
        perspective="sideToMove",
        player_rating=1600,
        opponent_rating=1600,
        speed="rapid",
        db_path=db_path,
        allow_stockfish=False,
    )

    assert board.turn == chess.BLACK
    assert result.winrate == 45.0


def test_rare_exact_stats_are_not_reported_as_lichess_exact(tmp_path) -> None:
    db_path = tmp_path / "winrates.sqlite"
    board = chess.Board()
    create_stats_db(db_path)
    insert_stats(
        db_path,
        fen_key=normalize_fen_for_stats(board),
        speed="bullet",
        rating_bucket=1200,
        white_wins=4,
        draws=2,
        black_wins=3,
    )

    result = get_winrate(
        fen=board.fen(),
        perspective="white",
        player_rating=1200,
        opponent_rating=1200,
        speed="bullet",
        db_path=db_path,
        allow_stockfish=False,
    )

    assert result.source == "fallback"
    assert result.confidence == "low"


def test_stockfish_wdl_is_strict_win_probability_not_expected_score() -> None:
    board = chess.Board()
    line = EngineLine(
        stockfish_rank=1,
        move_uci="e2e4",
        eval_cp=20,
        mate_in=None,
        pv=["e2e4"],
        wdl=(420, 510, 70),
    )

    white = get_winrate(fen=board.fen(), perspective="white", stockfish_line=line, allow_stockfish=False)
    black = get_winrate(fen=board.fen(), perspective="black", stockfish_line=line, allow_stockfish=False)

    assert white.source == "stockfish"
    assert white.winrate == 42.0
    assert black.winrate == 7.0


def test_checkmate_position_returns_zero_for_mated_side() -> None:
    board = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")

    black = get_winrate(fen=board.fen(), perspective="black", allow_stockfish=False)
    white = get_winrate(fen=board.fen(), perspective="white", allow_stockfish=False)

    assert board.is_checkmate()
    assert black.winrate == 0.0
    assert white.winrate == 100.0
    assert black.confidence == "high"


def test_winrate_endpoint_rejects_invalid_fen() -> None:
    client = TestClient(app)

    response = client.post("/winrate", json={"fen": "not a fen", "perspective": "white"})

    assert response.status_code == 422


def create_stats_db(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE position_stats (
                fen_key TEXT NOT NULL,
                speed TEXT NOT NULL,
                rating_bucket INTEGER NOT NULL,
                white_wins INTEGER NOT NULL DEFAULT 0,
                draws INTEGER NOT NULL DEFAULT 0,
                black_wins INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (fen_key, speed, rating_bucket)
            )
            """
        )


def insert_stats(
    path,
    *,
    fen_key: str,
    speed: str,
    rating_bucket: int,
    white_wins: int,
    draws: int,
    black_wins: int,
) -> None:
    total = white_wins + draws + black_wins
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO position_stats (fen_key, speed, rating_bucket, white_wins, draws, black_wins, total)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fen_key, speed, rating_bucket, white_wins, draws, black_wins, total),
        )
