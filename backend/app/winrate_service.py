from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Mapping

import chess

from .stockfish_engine import EngineLine, StockfishEngine


WinratePerspective = Literal["white", "black", "sideToMove"]
WinrateSpeed = Literal["bullet", "blitz", "rapid", "classical"]
WinrateSource = Literal["lichess_exact", "lichess_model", "stockfish", "fallback"]
WinrateConfidence = Literal["high", "medium", "low"]

# Exact Lichess stats are only used above this minimum sample size. Draws stay
# in the denominator because this module estimates the real probability of
# winning, not expected score.
EXACT_MIN_GAMES = 25
EXACT_MEDIUM_GAMES = 60
EXACT_HIGH_GAMES = 200

DEFAULT_STOCKFISH_DEPTH = 12
DEFAULT_STOCKFISH_MOVETIME_MS = 350
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "lichess_winrates.sqlite"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "data" / "lichess_winrate_model.json"

PIECE_VALUES_CP = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

MODEL_FEATURE_NAMES = [
    "bias",
    "material_pawns_white",
    "side_to_move_white",
    "legal_moves_scaled",
    "white_in_check",
    "black_in_check",
    "endgame_phase",
    "fullmove_scaled",
    "rating_avg_scaled",
    "rating_diff_white_scaled",
    "speed_bullet",
    "speed_blitz",
    "speed_rapid",
    "speed_classical",
]


@dataclass(frozen=True)
class WinrateResult:
    winrate: float
    perspective: WinratePerspective
    source: WinrateSource
    confidence: WinrateConfidence
    white_winrate: float | None = None
    black_winrate: float | None = None
    side_to_move_winrate: float | None = None
    sample_size: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "winrate": round(self.winrate, 1),
            "perspective": self.perspective,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PositionStats:
    white_wins: int
    draws: int
    black_wins: int
    total: int


def get_winrate(
    *,
    fen: str,
    perspective: WinratePerspective = "sideToMove",
    player_rating: int | None = None,
    opponent_rating: int | None = None,
    speed: WinrateSpeed | None = None,
    db_path: str | Path | None = None,
    model_path: str | Path | None = None,
    stockfish_line: Any | None = None,
    allow_stockfish: bool = True,
) -> WinrateResult:
    board = chess.Board(fen)
    normalized_perspective = normalize_perspective(perspective)
    requested_side = side_for_perspective(board, normalized_perspective)

    if board.is_game_over(claim_draw=True):
        return terminal_winrate(board, normalized_perspective, requested_side)

    fen_key = normalize_fen_for_stats(board)
    exact_stats = lookup_lichess_stats(
        fen_key=fen_key,
        speed=speed,
        rating_bucket=rating_bucket_for(player_rating, opponent_rating),
        db_path=db_path,
    )
    if exact_stats is not None and exact_stats.total >= EXACT_MIN_GAMES:
        return result_from_stats(
            stats=exact_stats,
            board=board,
            perspective=normalized_perspective,
            requested_side=requested_side,
        )

    model_result = predict_with_lichess_model(
        board=board,
        perspective=normalized_perspective,
        requested_side=requested_side,
        player_rating=player_rating,
        opponent_rating=opponent_rating,
        speed=speed,
        model_path=model_path,
    )
    if model_result is not None:
        return model_result

    if stockfish_line is not None:
        return result_from_stockfish_line(
            board=board,
            perspective=normalized_perspective,
            requested_side=requested_side,
            line=stockfish_line,
        )

    if allow_stockfish:
        try:
            depth = int(os.getenv("WINRATE_STOCKFISH_DEPTH", str(DEFAULT_STOCKFISH_DEPTH)))
            movetime_ms = int(os.getenv("WINRATE_STOCKFISH_MOVETIME_MS", str(DEFAULT_STOCKFISH_MOVETIME_MS)))
            lines = StockfishEngine().analyze(
                fen=fen,
                multipv=1,
                depth=max(1, depth),
                movetime_ms=max(50, movetime_ms),
            )
            if lines:
                return result_from_stockfish_line(
                    board=board,
                    perspective=normalized_perspective,
                    requested_side=requested_side,
                    line=lines[0],
                )
        except Exception:
            pass

    return fallback_winrate(board, normalized_perspective, requested_side)


def normalize_perspective(value: str | None) -> WinratePerspective:
    if value in {"white", "black", "sideToMove"}:
        return value  # type: ignore[return-value]
    return "sideToMove"


def side_for_perspective(board: chess.Board, perspective: WinratePerspective) -> chess.Color:
    if perspective == "white":
        return chess.WHITE
    if perspective == "black":
        return chess.BLACK
    return board.turn


def side_name(side: chess.Color) -> Literal["white", "black"]:
    return "white" if side == chess.WHITE else "black"


def normalize_fen_for_stats(board_or_fen: chess.Board | str) -> str:
    board = chess.Board(board_or_fen) if isinstance(board_or_fen, str) else board_or_fen
    castling = board.castling_xfen() if board.castling_rights else "-"
    ep_square = chess.square_name(board.ep_square) if board.ep_square is not None and board.has_legal_en_passant() else "-"
    turn = "w" if board.turn == chess.WHITE else "b"
    return f"{board.board_fen()} {turn} {castling} {ep_square}"


def rating_bucket_for(player_rating: int | None, opponent_rating: int | None) -> int | None:
    ratings = [rating for rating in (player_rating, opponent_rating) if rating is not None]
    if not ratings:
        return None
    average = sum(ratings) / len(ratings)
    return max(600, min(3200, int(round(average / 200.0) * 200)))


def lookup_lichess_stats(
    *,
    fen_key: str,
    speed: WinrateSpeed | None,
    rating_bucket: int | None,
    db_path: str | Path | None = None,
) -> PositionStats | None:
    path = resolve_existing_path(db_path, "LICHESS_WINRATE_DB", DEFAULT_DB_PATH)
    if path is None:
        return None

    filters: list[tuple[str, tuple[Any, ...]]] = []
    if speed is not None and rating_bucket is not None:
        filters.append(("speed = ? AND rating_bucket = ?", (speed, rating_bucket)))
    if speed is not None:
        filters.append(("speed = ?", (speed,)))
    if rating_bucket is not None:
        filters.append(("rating_bucket = ?", (rating_bucket,)))
    filters.append(("1 = 1", ()))

    best: PositionStats | None = None
    try:
        with sqlite3.connect(path) as connection:
            for where_sql, params in filters:
                row = connection.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(white_wins), 0),
                        COALESCE(SUM(draws), 0),
                        COALESCE(SUM(black_wins), 0),
                        COALESCE(SUM(total), 0)
                    FROM position_stats
                    WHERE fen_key = ? AND {where_sql}
                    """,
                    (fen_key, *params),
                ).fetchone()
                stats = PositionStats(
                    white_wins=int(row[0] or 0),
                    draws=int(row[1] or 0),
                    black_wins=int(row[2] or 0),
                    total=int(row[3] or 0),
                )
                if stats.total >= EXACT_MIN_GAMES:
                    return stats
                if best is None or stats.total > best.total:
                    best = stats
    except sqlite3.Error:
        return None

    return best if best is not None and best.total > 0 else None


def result_from_stats(
    *,
    stats: PositionStats,
    board: chess.Board,
    perspective: WinratePerspective,
    requested_side: chess.Color,
) -> WinrateResult:
    white = percent(stats.white_wins, stats.total)
    black = percent(stats.black_wins, stats.total)
    side_to_move = white if board.turn == chess.WHITE else black
    requested = white if requested_side == chess.WHITE else black
    return WinrateResult(
        winrate=requested,
        perspective=perspective,
        source="lichess_exact",
        confidence=confidence_from_sample_size(stats.total),
        white_winrate=white,
        black_winrate=black,
        side_to_move_winrate=side_to_move,
        sample_size=stats.total,
    )


def predict_with_lichess_model(
    *,
    board: chess.Board,
    perspective: WinratePerspective,
    requested_side: chess.Color,
    player_rating: int | None,
    opponent_rating: int | None,
    speed: WinrateSpeed | None,
    model_path: str | Path | None,
) -> WinrateResult | None:
    path = resolve_existing_path(model_path, "LICHESS_WINRATE_MODEL_PATH", DEFAULT_MODEL_PATH)
    if path is None:
        return None
    model = load_model(str(path))
    if not model:
        return None
    targets = model.get("targets")
    if not isinstance(targets, Mapping):
        return None

    features = build_model_features(
        board=board,
        player_rating=player_rating,
        opponent_rating=opponent_rating,
        speed=speed,
        perspective=perspective,
    )
    white = predict_target_probability(targets.get("white"), features, model)
    black = predict_target_probability(targets.get("black"), features, model)
    if white is None and black is None:
        return None
    if white is None and black is not None:
        white = max(0.0, 100.0 - black)
    if black is None and white is not None:
        black = max(0.0, 100.0 - white)
    assert white is not None and black is not None

    side_to_move = white if board.turn == chess.WHITE else black
    requested = white if requested_side == chess.WHITE else black
    confidence = str(model.get("confidence", "medium"))
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    return WinrateResult(
        winrate=requested,
        perspective=perspective,
        source="lichess_model",
        confidence=confidence,  # type: ignore[arg-type]
        white_winrate=white,
        black_winrate=black,
        side_to_move_winrate=side_to_move,
    )


def result_from_stockfish_line(
    *,
    board: chess.Board,
    perspective: WinratePerspective,
    requested_side: chess.Color,
    line: Any,
) -> WinrateResult:
    eval_cp, mate_in, wdl = extract_stockfish_score(line)
    side_to_move_win, opponent_win = stockfish_side_winrates(eval_cp=eval_cp, mate_in=mate_in, wdl=wdl)
    if board.turn == chess.WHITE:
        white = side_to_move_win
        black = opponent_win
    else:
        white = opponent_win
        black = side_to_move_win
    requested = white if requested_side == chess.WHITE else black
    return WinrateResult(
        winrate=requested,
        perspective=perspective,
        source="stockfish",
        confidence="medium" if mate_in is None else "high",
        white_winrate=white,
        black_winrate=black,
        side_to_move_winrate=side_to_move_win,
    )


def extract_stockfish_score(line: Any) -> tuple[int | None, int | None, list[int] | tuple[int, int, int] | None]:
    if isinstance(line, EngineLine):
        return line.eval_cp, line.mate_in, line.wdl
    if isinstance(line, Mapping):
        return (
            int(line["evalCp"]) if line.get("evalCp") is not None else None,
            int(line["mateIn"]) if line.get("mateIn") is not None else None,
            line.get("wdl"),
        )
    eval_cp = getattr(line, "eval_cp", None)
    mate_in = getattr(line, "mate_in", None)
    wdl = getattr(line, "wdl", None)
    return (
        int(eval_cp) if eval_cp is not None else None,
        int(mate_in) if mate_in is not None else None,
        wdl,
    )


def stockfish_side_winrates(
    *,
    eval_cp: int | None,
    mate_in: int | None,
    wdl: list[int] | tuple[int, int, int] | None,
) -> tuple[float, float]:
    normalized_wdl = normalize_wdl(wdl)
    if normalized_wdl is not None:
        wins, _draws, losses = normalized_wdl
        total = sum(normalized_wdl)
        if total > 0:
            return percent(wins, total), percent(losses, total)

    if mate_in is not None:
        certainty = mate_certainty(mate_in)
        if mate_in > 0:
            return certainty, 100.0 - certainty
        return 100.0 - certainty, certainty

    if eval_cp is None:
        return 50.0, 50.0
    side_win = cp_to_win_percent(eval_cp)
    return side_win, 100.0 - side_win


def fallback_winrate(board: chess.Board, perspective: WinratePerspective, requested_side: chess.Color) -> WinrateResult:
    white_cp = heuristic_cp_from_board(board)
    white = cp_to_win_percent(white_cp)
    black = cp_to_win_percent(-white_cp)
    side_to_move = white if board.turn == chess.WHITE else black
    requested = white if requested_side == chess.WHITE else black
    return WinrateResult(
        winrate=requested,
        perspective=perspective,
        source="fallback",
        confidence="low",
        white_winrate=white,
        black_winrate=black,
        side_to_move_winrate=side_to_move,
    )


def terminal_winrate(board: chess.Board, perspective: WinratePerspective, requested_side: chess.Color) -> WinrateResult:
    if board.is_checkmate():
        winner = not board.turn
        white = 100.0 if winner == chess.WHITE else 0.0
        black = 100.0 if winner == chess.BLACK else 0.0
    else:
        white = 0.0
        black = 0.0
    side_to_move = white if board.turn == chess.WHITE else black
    requested = white if requested_side == chess.WHITE else black
    return WinrateResult(
        winrate=requested,
        perspective=perspective,
        source="fallback",
        confidence="high",
        white_winrate=white,
        black_winrate=black,
        side_to_move_winrate=side_to_move,
    )


def build_model_features(
    *,
    board: chess.Board,
    player_rating: int | None,
    opponent_rating: int | None,
    speed: WinrateSpeed | None,
    perspective: WinratePerspective,
) -> dict[str, float]:
    material_cp = material_balance_cp(board)
    legal_moves = board.legal_moves.count()
    white_in_check = is_color_in_check(board, chess.WHITE)
    black_in_check = is_color_in_check(board, chess.BLACK)
    rating_avg, rating_diff_white = rating_features(
        board=board,
        player_rating=player_rating,
        opponent_rating=opponent_rating,
        perspective=perspective,
    )
    features = {
        "bias": 1.0,
        "material_pawns_white": material_cp / 1000.0,
        "side_to_move_white": 1.0 if board.turn == chess.WHITE else 0.0,
        "legal_moves_scaled": min(1.5, legal_moves / 40.0),
        "white_in_check": 1.0 if white_in_check else 0.0,
        "black_in_check": 1.0 if black_in_check else 0.0,
        "endgame_phase": 1.0 if is_endgame(board) else 0.0,
        "fullmove_scaled": min(1.5, board.fullmove_number / 60.0),
        "rating_avg_scaled": 0.0 if rating_avg is None else (rating_avg - 1500.0) / 800.0,
        "rating_diff_white_scaled": 0.0 if rating_diff_white is None else rating_diff_white / 400.0,
        "speed_bullet": 1.0 if speed == "bullet" else 0.0,
        "speed_blitz": 1.0 if speed == "blitz" else 0.0,
        "speed_rapid": 1.0 if speed == "rapid" else 0.0,
        "speed_classical": 1.0 if speed == "classical" else 0.0,
    }
    return features


def rating_features(
    *,
    board: chess.Board,
    player_rating: int | None,
    opponent_rating: int | None,
    perspective: WinratePerspective,
) -> tuple[float | None, float | None]:
    ratings = [rating for rating in (player_rating, opponent_rating) if rating is not None]
    rating_avg = sum(ratings) / len(ratings) if ratings else None
    if player_rating is None or opponent_rating is None:
        return rating_avg, None

    if perspective == "white":
        return rating_avg, float(player_rating - opponent_rating)
    if perspective == "black":
        return rating_avg, float(opponent_rating - player_rating)
    if board.turn == chess.WHITE:
        return rating_avg, float(player_rating - opponent_rating)
    return rating_avg, float(opponent_rating - player_rating)


def predict_target_probability(target: Any, features: Mapping[str, float], model: Mapping[str, Any]) -> float | None:
    if not isinstance(target, Mapping):
        return None
    weights = target.get("weights", target)
    if not isinstance(weights, Mapping):
        return None
    logit = 0.0
    for feature_name in MODEL_FEATURE_NAMES:
        try:
            logit += float(weights.get(feature_name, 0.0)) * float(features.get(feature_name, 0.0))
        except (TypeError, ValueError):
            return None
    temperature = 1.0
    calibration = model.get("calibration")
    if isinstance(calibration, Mapping):
        try:
            temperature = max(0.05, float(calibration.get("temperature", 1.0)))
        except (TypeError, ValueError):
            temperature = 1.0
    return clamp_percent(sigmoid(logit / temperature) * 100.0)


@lru_cache(maxsize=8)
def load_model(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_existing_path(path: str | Path | None, env_name: str, default_path: Path) -> Path | None:
    raw = path or os.getenv(env_name) or default_path
    resolved = Path(raw)
    return resolved if resolved.exists() and resolved.is_file() else None


def confidence_from_sample_size(total: int) -> WinrateConfidence:
    if total >= EXACT_HIGH_GAMES:
        return "high"
    if total >= EXACT_MEDIUM_GAMES:
        return "medium"
    return "low"


def percent(count: int | float, total: int | float) -> float:
    if total <= 0:
        return 0.0
    return clamp_percent(float(count) * 100.0 / float(total))


def normalize_wdl(wdl: list[int] | tuple[int, int, int] | None) -> tuple[int, int, int] | None:
    if not wdl or len(wdl) != 3:
        return None
    try:
        wins, draws, losses = (max(0, int(value)) for value in wdl)
    except (TypeError, ValueError):
        return None
    return wins, draws, losses


def cp_to_win_percent(cp: int | float) -> float:
    capped = max(-1500.0, min(1500.0, float(cp)))
    return clamp_percent(50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * capped)) - 1.0))


def mate_certainty(mate_in: int) -> float:
    distance = max(1, abs(int(mate_in)))
    return clamp_percent(max(96.0, 99.8 - min(distance - 1, 10) * 0.32))


def sigmoid(value: float) -> float:
    if value >= 0:
        factor = math.exp(-value)
        return 1.0 / (1.0 + factor)
    factor = math.exp(value)
    return factor / (1.0 + factor)


def clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def heuristic_cp_from_board(board: chess.Board) -> int:
    material = material_balance_cp(board)
    mobility = mobility_balance(board) * 4
    king_safety = 0
    if is_color_in_check(board, chess.WHITE):
        king_safety -= 45
    if is_color_in_check(board, chess.BLACK):
        king_safety += 45
    return int(max(-1600, min(1600, material + mobility + king_safety)))


def material_balance_cp(board: chess.Board) -> int:
    score = 0
    for square, piece in board.piece_map().items():
        value = PIECE_VALUES_CP[piece.piece_type]
        score += value if piece.color == chess.WHITE else -value
    return score


def mobility_balance(board: chess.Board) -> int:
    clone = board.copy(stack=False)
    clone.turn = chess.WHITE
    white_moves = clone.legal_moves.count()
    clone.turn = chess.BLACK
    black_moves = clone.legal_moves.count()
    return white_moves - black_moves


def is_color_in_check(board: chess.Board, color: chess.Color) -> bool:
    clone = board.copy(stack=False)
    clone.turn = color
    return clone.is_check()


def is_endgame(board: chess.Board) -> bool:
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    non_pawn_material = 0
    for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        non_pawn_material += PIECE_VALUES_CP[piece_type] * (
            len(board.pieces(piece_type, chess.WHITE)) + len(board.pieces(piece_type, chess.BLACK))
        )
    return queens == 0 or non_pawn_material <= 2600
