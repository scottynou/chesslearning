import pytest
import chess
from pydantic import ValidationError

from app.schemas import AnalyzeRequest, CandidateMove, ExplainRequest


def test_analyze_request_clamps_max_moves() -> None:
    request = AnalyzeRequest(fen=chess.STARTING_FEN, elo=1200, maxMoves=30, engineDepth=14)
    assert request.max_moves == 10


def test_analyze_request_rejects_invalid_fen() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(fen="not a fen", elo=1200, maxMoves=10, engineDepth=14)


def test_explain_request_accepts_candidate_shape() -> None:
    candidate = CandidateMove(
        rank=1,
        moveUci="e2e4",
        moveSan="e4",
        stockfishRank=1,
        evalCp=30,
        mateIn=None,
        pv=["e2e4", "e7e5"],
        coachScore=90,
        engineScore=88,
        humanLikelihood=75,
        simplicityScore=92,
        riskPenalty=5,
        difficulty="easy",
        risk="low",
        summary="Prend de l'espace au centre.",
    )
    request = ExplainRequest(
        fen="rn1qkbnr/pppbpppp/8/3p4/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
        elo=1200,
        selectedMove=candidate,
        allCandidates=[candidate],
        moveHistoryPgn="1. e4 d5 2. Nf3 Bd7",
    )

    assert request.selected_move.move_uci == "e2e4"
