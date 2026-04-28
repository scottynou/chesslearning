from __future__ import annotations

import threading
from pathlib import Path
from time import sleep

from app.stockfish_engine import EngineLine, StockfishEngine


class FakePersistentProcess:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, *, fen: str, multipv: int, depth: int, movetime_ms: int | None):
        self.calls += 1
        sleep(0.05)
        return [EngineLine(1, "e2e4", 20, None, ["e2e4"])]


def test_stockfish_analysis_cache_includes_movetime(monkeypatch) -> None:
    import app.stockfish_engine as stockfish_engine

    fake_process = FakePersistentProcess()
    stockfish_engine._analysis_cache.clear()
    stockfish_engine._inflight_analyses.clear()
    monkeypatch.setattr(StockfishEngine, "_resolve_executable", lambda self: Path("fake-stockfish"))
    monkeypatch.setattr(stockfish_engine, "_get_persistent_process", lambda executable, timeout: fake_process)

    engine = StockfishEngine()
    engine.analyze("startpos", multipv=1, depth=6, movetime_ms=700)
    engine.analyze("startpos", multipv=1, depth=6, movetime_ms=700)
    engine.analyze("startpos", multipv=1, depth=6, movetime_ms=900)

    assert fake_process.calls == 2


def test_stockfish_analysis_coalesces_identical_inflight_requests(monkeypatch) -> None:
    import app.stockfish_engine as stockfish_engine

    fake_process = FakePersistentProcess()
    stockfish_engine._analysis_cache.clear()
    stockfish_engine._inflight_analyses.clear()
    monkeypatch.setattr(StockfishEngine, "_resolve_executable", lambda self: Path("fake-stockfish"))
    monkeypatch.setattr(stockfish_engine, "_get_persistent_process", lambda executable, timeout: fake_process)

    engine = StockfishEngine(timeout_seconds=2)
    results: list[list[EngineLine]] = []
    threads = [
        threading.Thread(target=lambda: results.append(engine.analyze("startpos", multipv=1, depth=6, movetime_ms=700)))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert fake_process.calls == 1
    assert len(results) == 2
    assert all(result[0].move_uci == "e2e4" for result in results)
