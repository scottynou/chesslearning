from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from time import monotonic


class StockfishConfigurationError(RuntimeError):
    pass


class StockfishRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineLine:
    stockfish_rank: int
    move_uci: str
    eval_cp: int | None
    mate_in: int | None
    pv: list[str]


_ANALYSIS_CACHE_TTL_SECONDS = 120
_ANALYSIS_CACHE_MAX_ITEMS = 256
_analysis_cache_lock = threading.Lock()
_analysis_cache: dict[tuple[str, str, int, int], tuple[float, list[EngineLine]]] = {}


class StockfishEngine:
    def __init__(self, stockfish_path: str | None = None, timeout_seconds: float = 12.0) -> None:
        self.stockfish_path = stockfish_path or os.getenv("STOCKFISH_PATH", "")
        self.timeout_seconds = timeout_seconds

    def analyze(self, fen: str, multipv: int, depth: int) -> list[EngineLine]:
        executable = self._resolve_executable()
        cache_key = (str(executable), fen, multipv, depth)
        cached = _get_cached_analysis(cache_key)
        if cached is not None:
            return cached

        process = subprocess.Popen(
            [str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        if process.stdin is None or process.stdout is None:
            raise StockfishRuntimeError("Unable to communicate with Stockfish.")

        output: queue.Queue[str] = queue.Queue()
        reader = threading.Thread(target=self._read_stdout, args=(process.stdout, output), daemon=True)
        reader.start()

        try:
            self._send(process, "uci")
            self._wait_for(output, "uciok")
            self._send(process, f"setoption name MultiPV value {multipv}")
            self._send(process, "isready")
            self._wait_for(output, "readyok")
            self._send(process, "ucinewgame")
            self._send(process, f"position fen {fen}")
            self._send(process, f"go depth {depth}")
            lines = self._collect_analysis(output)
        finally:
            self._send(process, "quit", ignore_broken_pipe=True)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

        result = self._parse_engine_lines(lines)
        _set_cached_analysis(cache_key, result)
        return result

    def _resolve_executable(self) -> Path:
        candidates = [
            self.stockfish_path,
            shutil.which("stockfish"),
            "/usr/games/stockfish",
            "/usr/bin/stockfish",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            executable = Path(candidate)
            if executable.exists() and executable.is_file():
                return executable
        raise StockfishConfigurationError(
            "Stockfish is not configured. Set STOCKFISH_PATH, install stockfish in PATH, or use /usr/games/stockfish."
        )

    @staticmethod
    def _send(process: subprocess.Popen[str], command: str, ignore_broken_pipe: bool = False) -> None:
        try:
            assert process.stdin is not None
            process.stdin.write(command + "\n")
            process.stdin.flush()
        except BrokenPipeError:
            if not ignore_broken_pipe:
                raise

    @staticmethod
    def _read_stdout(stdout, output: queue.Queue[str]) -> None:
        for line in stdout:
            output.put(line.strip())

    def _wait_for(self, output: queue.Queue[str], expected: str) -> None:
        deadline = threading.Event()
        timer = threading.Timer(self.timeout_seconds, deadline.set)
        timer.start()
        try:
            while not deadline.is_set():
                try:
                    line = output.get(timeout=0.05)
                except queue.Empty:
                    continue
                if line == expected:
                    return
        finally:
            timer.cancel()
        raise StockfishRuntimeError(f"Timed out waiting for Stockfish response: {expected}")

    def _collect_analysis(self, output: queue.Queue[str]) -> list[str]:
        collected: list[str] = []
        deadline = threading.Event()
        timer = threading.Timer(self.timeout_seconds, deadline.set)
        timer.start()
        try:
            while not deadline.is_set():
                try:
                    line = output.get(timeout=0.05)
                except queue.Empty:
                    continue
                collected.append(line)
                if line.startswith("bestmove"):
                    return collected
        finally:
            timer.cancel()
        raise StockfishRuntimeError("Timed out while Stockfish was analyzing the position.")

    @staticmethod
    def _parse_engine_lines(lines: list[str]) -> list[EngineLine]:
        by_rank: dict[int, EngineLine] = {}
        for line in lines:
            tokens = line.split()
            if not tokens or tokens[0] != "info" or " pv " not in f" {line} ":
                continue

            rank = 1
            if "multipv" in tokens:
                rank = int(tokens[tokens.index("multipv") + 1])

            eval_cp: int | None = None
            mate_in: int | None = None
            if "score" in tokens:
                score_index = tokens.index("score")
                score_type = tokens[score_index + 1]
                score_value = int(tokens[score_index + 2])
                if score_type == "cp":
                    eval_cp = score_value
                elif score_type == "mate":
                    mate_in = score_value

            pv_index = tokens.index("pv")
            pv = tokens[pv_index + 1 :]
            if not pv:
                continue

            by_rank[rank] = EngineLine(
                stockfish_rank=rank,
                move_uci=pv[0],
                eval_cp=eval_cp,
                mate_in=mate_in,
                pv=pv,
            )

        return [by_rank[index] for index in sorted(by_rank)]


def _get_cached_analysis(key: tuple[str, str, int, int]) -> list[EngineLine] | None:
    now = monotonic()
    with _analysis_cache_lock:
        entry = _analysis_cache.get(key)
        if entry is None:
            return None
        created_at, lines = entry
        if now - created_at > _ANALYSIS_CACHE_TTL_SECONDS:
            _analysis_cache.pop(key, None)
            return None
        return list(lines)


def _set_cached_analysis(key: tuple[str, str, int, int], lines: list[EngineLine]) -> None:
    with _analysis_cache_lock:
        if len(_analysis_cache) >= _ANALYSIS_CACHE_MAX_ITEMS:
            oldest_key = min(_analysis_cache, key=lambda item: _analysis_cache[item][0])
            _analysis_cache.pop(oldest_key, None)
        _analysis_cache[key] = (monotonic(), list(lines))
