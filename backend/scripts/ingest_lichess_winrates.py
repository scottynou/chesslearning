from __future__ import annotations

import argparse
import io
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.winrate_service import normalize_fen_for_stats, rating_bucket_for  # noqa: E402


RESULT_TO_COUNTER = {
    "1-0": "white_wins",
    "0-1": "black_wins",
    "1/2-1/2": "draws",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream Lichess PGN or PGN.zst files into an aggregated position winrate SQLite database."
    )
    parser.add_argument("pgn_files", nargs="+", type=Path, help="Lichess .pgn or .pgn.zst exports")
    parser.add_argument("--db", type=Path, default=ROOT / "app" / "data" / "lichess_winrates.sqlite")
    parser.add_argument("--max-plies", type=int, default=80, help="Maximum plies indexed per game")
    parser.add_argument("--flush-games", type=int, default=1000, help="SQLite flush cadence")
    parser.add_argument("--include-unrated", action="store_true", help="Do not skip unrated games")
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as connection:
        initialize_database(connection)
        batch: Counter[tuple[str, str, int, str]] = Counter()
        games_seen = 0
        games_indexed = 0

        for pgn_file in args.pgn_files:
            with open_pgn_stream(pgn_file) as stream:
                while True:
                    game = chess.pgn.read_game(stream)
                    if game is None:
                        break
                    games_seen += 1
                    if not should_index_game(game, include_unrated=args.include_unrated):
                        continue
                    add_game_to_batch(batch, game, max_plies=args.max_plies)
                    games_indexed += 1
                    if games_indexed % args.flush_games == 0:
                        flush_batch(connection, batch)
                        print(f"Indexed {games_indexed:,} games ({games_seen:,} read)", flush=True)

        flush_batch(connection, batch)
        connection.execute("PRAGMA optimize")
        print(f"Done. Indexed {games_indexed:,} games from {games_seen:,} read into {args.db}")


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS position_stats (
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
    connection.execute("CREATE INDEX IF NOT EXISTS idx_position_stats_fen ON position_stats (fen_key)")


def open_pgn_stream(path: Path):
    raw = path.open("rb")
    if path.suffix.lower() != ".zst":
        return io.TextIOWrapper(raw, encoding="utf-8", errors="replace")

    try:
        import zstandard as zstd
    except ImportError as exc:
        raw.close()
        raise SystemExit("Install zstandard to read .zst exports: pip install zstandard") from exc

    dctx = zstd.ZstdDecompressor()
    reader = dctx.stream_reader(raw)
    return io.TextIOWrapper(reader, encoding="utf-8", errors="replace")


def should_index_game(game: chess.pgn.Game, *, include_unrated: bool) -> bool:
    headers = game.headers
    if headers.get("Variant", "Standard") != "Standard":
        return False
    if not include_unrated and headers.get("Rated", "True").lower() not in {"true", "yes"}:
        return False
    return headers.get("Result") in RESULT_TO_COUNTER


def add_game_to_batch(batch: Counter[tuple[str, str, int, str]], game: chess.pgn.Game, *, max_plies: int) -> None:
    headers = game.headers
    result_counter = RESULT_TO_COUNTER[str(headers["Result"])]
    speed = speed_from_headers(headers)
    rating_bucket = rating_bucket_for(parse_int(headers.get("WhiteElo")), parse_int(headers.get("BlackElo"))) or 0
    board = game.board()

    for ply, move in enumerate(game.mainline_moves()):
        if ply >= max_plies:
            break
        if board.is_valid():
            batch[(normalize_fen_for_stats(board), speed, rating_bucket, result_counter)] += 1
        if move not in board.legal_moves:
            break
        board.push(move)

    if board.is_valid() and max_plies > 0:
        batch[(normalize_fen_for_stats(board), speed, rating_bucket, result_counter)] += 1


def flush_batch(connection: sqlite3.Connection, batch: Counter[tuple[str, str, int, str]]) -> None:
    if not batch:
        return
    rows = []
    for (fen_key, speed, rating_bucket, counter), count in batch.items():
        white_wins = count if counter == "white_wins" else 0
        draws = count if counter == "draws" else 0
        black_wins = count if counter == "black_wins" else 0
        rows.append((fen_key, speed, rating_bucket, white_wins, draws, black_wins, count))

    connection.executemany(
        """
        INSERT INTO position_stats (fen_key, speed, rating_bucket, white_wins, draws, black_wins, total)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fen_key, speed, rating_bucket) DO UPDATE SET
            white_wins = white_wins + excluded.white_wins,
            draws = draws + excluded.draws,
            black_wins = black_wins + excluded.black_wins,
            total = total + excluded.total
        """,
        rows,
    )
    connection.commit()
    batch.clear()


def speed_from_headers(headers: chess.pgn.Headers) -> str:
    speed = headers.get("Speed", "").strip().lower()
    if speed in {"bullet", "blitz", "rapid", "classical"}:
        return speed

    event = headers.get("Event", "").lower()
    for candidate in ("bullet", "blitz", "rapid", "classical"):
        if candidate in event:
            return candidate

    time_control = headers.get("TimeControl", "")
    return speed_from_time_control(time_control)


def speed_from_time_control(time_control: str) -> str:
    if not time_control or time_control == "-":
        return "blitz"
    base, _, increment = time_control.partition("+")
    try:
        base_seconds = int(base)
        increment_seconds = int(increment or "0")
    except ValueError:
        return "blitz"
    estimated_seconds = base_seconds + increment_seconds * 40
    if estimated_seconds < 180:
        return "bullet"
    if estimated_seconds < 480:
        return "blitz"
    if estimated_seconds < 1500:
        return "rapid"
    return "classical"


def parse_int(value: str | None) -> int | None:
    try:
        return int(value or "")
    except ValueError:
        return None


if __name__ == "__main__":
    main()
