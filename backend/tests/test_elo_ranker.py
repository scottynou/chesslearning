import chess

from app.elo_ranker import compute_coach_score, rank_candidates, weights_for_elo
from app.stockfish_engine import EngineLine


def test_weights_for_elo_steps() -> None:
    assert weights_for_elo(600).engine_weight == 0.45
    assert weights_for_elo(1200).engine_weight == 0.60
    assert weights_for_elo(1800).engine_weight == 0.75
    assert weights_for_elo(2400).engine_weight == 0.85
    assert weights_for_elo(3200).engine_weight == 0.95


def test_coach_score_formula() -> None:
    score = compute_coach_score(
        elo=1200,
        engine_score=80,
        human_likelihood=70,
        simplicity_score=90,
        risk_penalty=10,
        pedagogy_bonus=3,
    )
    assert score == 78


def test_rank_candidates_sorts_and_limits() -> None:
    fen = chess.STARTING_FEN
    lines = [
        EngineLine(1, "g1f3", 30, None, ["g1f3", "d7d5", "d2d4"]),
        EngineLine(2, "e2e4", 25, None, ["e2e4", "e7e5", "g1f3"]),
        EngineLine(3, "b1c3", 12, None, ["b1c3", "d7d5", "e2e4"]),
        EngineLine(4, "h2h4", -35, None, ["h2h4", "d7d5", "h4h5"]),
    ]

    candidates = rank_candidates(fen, lines, elo=800, max_moves=2)

    assert len(candidates) == 2
    assert [candidate.rank for candidate in candidates] == [1, 2]
    assert all(candidate.move_uci in {"g1f3", "e2e4", "b1c3", "h2h4"} for candidate in candidates)


def test_rank_candidates_never_exceeds_ten() -> None:
    fen = chess.STARTING_FEN
    board = chess.Board(fen)
    lines = [
        EngineLine(index + 1, move.uci(), 20 - index, None, [move.uci()])
        for index, move in enumerate(board.legal_moves)
    ]

    assert len(rank_candidates(fen, lines, elo=1600, max_moves=50)) == 10
