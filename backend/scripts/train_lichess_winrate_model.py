from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import chess

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.winrate_service import MODEL_FEATURE_NAMES, build_model_features  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a small calibrated Lichess winrate logistic model.")
    parser.add_argument("--db", type=Path, default=ROOT / "app" / "data" / "lichess_winrates.sqlite")
    parser.add_argument("--out", type=Path, default=ROOT / "app" / "data" / "lichess_winrate_model.json")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=0.18)
    parser.add_argument("--l2", type=float, default=0.001)
    parser.add_argument("--min-position-games", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit for quick experiments")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    white_weights, white_loss, row_count, game_count = train_target(
        db_path=args.db,
        target="white",
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        l2=args.l2,
        min_position_games=args.min_position_games,
        limit=args.limit,
    )
    black_weights, black_loss, _, _ = train_target(
        db_path=args.db,
        target="black",
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        l2=args.l2,
        min_position_games=args.min_position_games,
        limit=args.limit,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    model = {
        "version": 1,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "featureNames": MODEL_FEATURE_NAMES,
        "confidence": "high" if game_count >= 1_000_000 else "medium" if game_count >= 100_000 else "low",
        "calibration": {"temperature": 1.0},
        "training": {
            "rows": row_count,
            "games": game_count,
            "epochs": args.epochs,
            "minPositionGames": args.min_position_games,
            "whiteLogLoss": round(white_loss, 6),
            "blackLogLoss": round(black_loss, 6),
        },
        "targets": {
            "white": {"weights": white_weights},
            "black": {"weights": black_weights},
        },
    }
    args.out.write_text(json.dumps(model, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {args.out} from {row_count:,} rows / {game_count:,} games")


def train_target(
    *,
    db_path: Path,
    target: str,
    epochs: int,
    learning_rate: float,
    l2: float,
    min_position_games: int,
    limit: int,
) -> tuple[dict[str, float], float, int, int]:
    weights = {name: 0.0 for name in MODEL_FEATURE_NAMES}
    row_count = 0
    game_count = 0
    last_loss = 0.0

    for _epoch in range(max(1, epochs)):
        gradients = {name: 0.0 for name in MODEL_FEATURE_NAMES}
        weight_total = 0.0
        loss_total = 0.0
        row_count = 0
        game_count = 0

        with sqlite3.connect(db_path) as connection:
            for fen_key, speed, rating_bucket, white_wins, black_wins, total in iter_training_rows(
                connection,
                min_position_games=min_position_games,
                limit=limit,
            ):
                try:
                    board = chess.Board(f"{fen_key} 0 1")
                except ValueError:
                    continue
                features = build_model_features(
                    board=board,
                    player_rating=rating_bucket or None,
                    opponent_rating=rating_bucket or None,
                    speed=speed if speed in {"bullet", "blitz", "rapid", "classical"} else None,
                    perspective="white",
                )
                observed_wins = white_wins if target == "white" else black_wins
                y = observed_wins / max(1, total)
                prediction = sigmoid(sum(weights[name] * features[name] for name in MODEL_FEATURE_NAMES))
                sample_weight = float(total)
                error = (prediction - y) * sample_weight
                for name in MODEL_FEATURE_NAMES:
                    gradients[name] += error * features[name]
                loss_total += sample_weight * binary_cross_entropy(y, prediction)
                weight_total += sample_weight
                row_count += 1
                game_count += int(total)

        if weight_total <= 0:
            break

        scale = learning_rate / weight_total
        for name in MODEL_FEATURE_NAMES:
            regularization = l2 * weights[name] if name != "bias" else 0.0
            weights[name] -= scale * (gradients[name] + regularization * weight_total)
        last_loss = loss_total / weight_total

    return {name: round(value, 8) for name, value in weights.items()}, last_loss, row_count, game_count


def iter_training_rows(
    connection: sqlite3.Connection,
    *,
    min_position_games: int,
    limit: int,
) -> Iterable[tuple[str, str, int, int, int, int]]:
    sql = """
        SELECT fen_key, speed, rating_bucket, white_wins, black_wins, total
        FROM position_stats
        WHERE total >= ?
        ORDER BY total DESC
    """
    if limit > 0:
        sql += " LIMIT ?"
        yield from connection.execute(sql, (min_position_games, limit))
    else:
        yield from connection.execute(sql, (min_position_games,))


def sigmoid(value: float) -> float:
    if value >= 0:
        factor = math.exp(-value)
        return 1.0 / (1.0 + factor)
    factor = math.exp(value)
    return factor / (1.0 + factor)


def binary_cross_entropy(y: float, prediction: float) -> float:
    p = min(1.0 - 1e-7, max(1e-7, prediction))
    return -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))


if __name__ == "__main__":
    main()
