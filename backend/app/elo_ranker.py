from __future__ import annotations

from dataclasses import dataclass

import chess

from .schemas import CandidateMove
from .stockfish_engine import EngineLine


@dataclass(frozen=True)
class EloWeights:
    engine_weight: float
    human_weight: float
    simplicity_weight: float
    risk_weight: float


PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


def weights_for_elo(elo: int) -> EloWeights:
    if elo < 1800:
        return EloWeights(0.68, 0.12, 0.18, 0.20)
    if elo < 2600:
        return EloWeights(0.80, 0.10, 0.10, 0.12)
    if elo < 3200:
        return EloWeights(0.72, 0.14, 0.10, 0.10)
    return EloWeights(0.96, 0.02, 0.01, 0.02)


def rank_candidates(fen: str, lines: list[EngineLine], elo: int, max_moves: int) -> list[CandidateMove]:
    board = chess.Board(fen)
    legal_lines = [line for line in lines if _is_legal_uci(board, line.move_uci)]
    if not legal_lines:
        return []

    best_score = max(_score_value(line) for line in legal_lines)
    weighted: list[CandidateMove] = []

    for line in legal_lines:
        move = chess.Move.from_uci(line.move_uci)
        move_san = board.san(move)
        engine_score = compute_engine_score(best_score, _score_value(line))
        simplicity_score = compute_simplicity_score(board, move, line)
        risk_penalty = compute_risk_penalty(line, simplicity_score)
        human_likelihood = compute_human_likelihood(elo, engine_score, simplicity_score, risk_penalty)
        coach_score = compute_coach_score(
            elo=elo,
            engine_score=engine_score,
            human_likelihood=human_likelihood,
            simplicity_score=simplicity_score,
            risk_penalty=risk_penalty,
            pedagogy_bonus=compute_pedagogy_bonus(simplicity_score, risk_penalty),
        )

        weighted.append(
            CandidateMove(
                rank=0,
                moveUci=line.move_uci,
                moveSan=move_san,
                stockfishRank=line.stockfish_rank,
                evalCp=line.eval_cp,
                mateIn=line.mate_in,
                wdl=list(line.wdl) if line.wdl is not None else None,
                pv=line.pv,
                coachScore=coach_score,
                engineScore=engine_score,
                humanLikelihood=human_likelihood,
                simplicityScore=simplicity_score,
                riskPenalty=risk_penalty,
                difficulty=classify_difficulty(simplicity_score, risk_penalty),
                risk=classify_risk(risk_penalty),
                summary=build_summary(board, move, line, simplicity_score),
            )
        )

    if elo >= 3200:
        sorted_candidates = sorted(
            weighted,
            key=lambda candidate: (
                candidate.stockfish_rank,
                -candidate.engine_score,
            ),
        )[: max(1, min(10, max_moves))]
    else:
        sorted_candidates = sorted(
            weighted,
            key=lambda candidate: (
                -candidate.coach_score,
                candidate.stockfish_rank,
                -candidate.engine_score,
            ),
        )[: max(1, min(10, max_moves))]

    return [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(sorted_candidates)
    ]


def compute_engine_score(best_score: int, move_score: int) -> int:
    delta = max(0, best_score - move_score)
    return _clamp(round(100 - delta / 8), 0, 100)


def compute_coach_score(
    *,
    elo: int,
    engine_score: int,
    human_likelihood: int,
    simplicity_score: int,
    risk_penalty: int,
    pedagogy_bonus: int = 0,
) -> int:
    weights = weights_for_elo(elo)
    score = (
        weights.engine_weight * engine_score
        + weights.human_weight * human_likelihood
        + weights.simplicity_weight * simplicity_score
        - weights.risk_weight * risk_penalty
        + pedagogy_bonus
    )
    return _clamp(round(score), 0, 100)


def compute_simplicity_score(board: chess.Board, move: chess.Move, line: EngineLine) -> int:
    piece = board.piece_at(move.from_square)
    if piece is None:
        return 0

    score = 48
    if board.is_castling(move):
        score += 24
    if _is_development_move(board, move, piece):
        score += 18
    if chess.square_name(move.to_square) in {"d4", "e4", "d5", "e5"}:
        score += 16
    if piece.piece_type == chess.PAWN and abs(chess.square_rank(move.to_square) - chess.square_rank(move.from_square)) <= 2:
        score += 10
    if board.is_capture(move):
        captured = board.piece_at(move.to_square)
        if captured is None and board.is_en_passant(move):
            captured_value = 1
        else:
            captured_value = PIECE_VALUES.get(captured.piece_type, 0) if captured else 0
        attacker_value = PIECE_VALUES.get(piece.piece_type, 0)
        score += 14 if captured_value >= attacker_value else 7
    if board.gives_check(move):
        score += 7
    if len(line.pv) <= 3:
        score += 8
    if len(line.pv) >= 8:
        score -= 10
    if piece.piece_type == chess.QUEEN and board.fullmove_number <= 6:
        score -= 12

    return _clamp(score, 0, 100)


def compute_risk_penalty(line: EngineLine, simplicity_score: int) -> int:
    penalty = 5
    if len(line.pv) > 8:
        penalty += 18
    elif len(line.pv) > 5:
        penalty += 9
    if simplicity_score < 45:
        penalty += 14
    if line.stockfish_rank > 6:
        penalty += 8
    if line.mate_in is not None and abs(line.mate_in) > 3:
        penalty += 10
    return _clamp(penalty, 0, 100)


def compute_human_likelihood(elo: int, engine_score: int, simplicity_score: int, risk_penalty: int) -> int:
    if elo < 1800:
        score = 0.42 * engine_score + 0.48 * simplicity_score - 0.32 * risk_penalty + 10
    elif elo < 2600:
        score = 0.64 * engine_score + 0.26 * simplicity_score - 0.18 * risk_penalty + 8
    elif elo < 3200:
        score = 0.70 * engine_score + 0.22 * simplicity_score - 0.12 * risk_penalty + 8
    else:
        score = 0.96 * engine_score + 0.03 * simplicity_score - 0.04 * risk_penalty + 3
    return _clamp(round(score), 0, 100)


def compute_pedagogy_bonus(simplicity_score: int, risk_penalty: int) -> int:
    if simplicity_score >= 75 and risk_penalty <= 15:
        return 6
    if simplicity_score >= 65 and risk_penalty <= 25:
        return 3
    return 0


def classify_difficulty(simplicity_score: int, risk_penalty: int) -> str:
    if simplicity_score >= 72 and risk_penalty <= 18:
        return "easy"
    if simplicity_score >= 50 and risk_penalty <= 35:
        return "medium"
    return "hard"


def classify_risk(risk_penalty: int) -> str:
    if risk_penalty <= 18:
        return "low"
    if risk_penalty <= 35:
        return "medium"
    return "high"


def build_summary(board: chess.Board, move: chess.Move, line: EngineLine, simplicity_score: int) -> str:
    piece = board.piece_at(move.from_square)
    if piece is None:
        return "Coup légal proposé par le moteur."
    if board.is_castling(move):
        return "Met le roi à l'abri et connecte les tours."
    if board.is_capture(move):
        return "Gagne ou échange du matériel avec une idée concrète."
    if _is_development_move(board, move, piece):
        return "Développe une pièce et prépare un plan simple."
    if chess.square_name(move.to_square) in {"d4", "e4", "d5", "e5"}:
        return "Prend de l'espace au centre et limite les réponses adverses."
    if simplicity_score < 45:
        return "Coup plus exigeant qui demande de suivre la variante avec précision."
    return "Améliore la position sans créer de risque immédiat."


def _score_value(line: EngineLine) -> int:
    if line.mate_in is not None:
        sign = 1 if line.mate_in > 0 else -1
        return sign * (100_000 - abs(line.mate_in) * 1_000)
    return line.eval_cp or 0


def _is_legal_uci(board: chess.Board, uci: str) -> bool:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return False
    return move in board.legal_moves


def _is_development_move(board: chess.Board, move: chess.Move, piece: chess.Piece) -> bool:
    if piece.piece_type not in {chess.KNIGHT, chess.BISHOP}:
        return False
    from_rank = chess.square_rank(move.from_square)
    home_rank = 0 if piece.color == chess.WHITE else 7
    return from_rank == home_rank and board.fullmove_number <= 12


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
