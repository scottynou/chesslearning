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
_analysis_cache: dict[tuple[str, str, int, int, int | None], tuple[float, list[EngineLine]]] = {}
_inflight_lock = threading.Lock()
_inflight_analyses: dict[tuple[str, str, int, int, int | None], "_InflightSlot"] = {}
_processes_lock = threading.Lock()
_persistent_processes: dict[str, "_PersistentStockfishProcess"] = {}


class _InflightSlot:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: list[EngineLine] | None = None
        self.error: BaseException | None = None


class StockfishEngine:
    def __init__(self, stockfish_path: str | None = None, timeout_seconds: float = 12.0) -> None:
        self.stockfish_path = stockfish_path or os.getenv("STOCKFISH_PATH", "")
        self.timeout_seconds = timeout_seconds

    def analyze(self, fen: str, multipv: int, depth: int, movetime_ms: int | None = None) -> list[EngineLine]:
        executable = self._resolve_executable()
        normalized_movetime = max(50, int(movetime_ms)) if movetime_ms else None
        cache_key = (str(executable), fen, multipv, depth, normalized_movetime)
        cached = _get_cached_analysis(cache_key)
        if cached is not None:
            return cached

        slot, owns_slot = _claim_inflight_analysis(cache_key)
        if not owns_slot:
            return _wait_for_inflight_analysis(cache_key, slot, self.timeout_seconds)

        try:
            process = _get_persistent_process(executable, self.timeout_seconds)
            result = process.analyze(fen=fen, multipv=multipv, depth=depth, movetime_ms=normalized_movetime)
        except BaseException as exc:
            _finish_inflight_analysis(cache_key, slot, None, exc)
            raise

        _set_cached_analysis(cache_key, result)
        _finish_inflight_analysis(cache_key, slot, result, None)
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


class _PersistentStockfishProcess:
    def __init__(self, executable: Path, timeout_seconds: float) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.lock = threading.Lock()
        self.process: subprocess.Popen[str] | None = None
        self.output: queue.Queue[str] = queue.Queue()
        self.reader: threading.Thread | None = None

    def analyze(self, *, fen: str, multipv: int, depth: int, movetime_ms: int | None) -> list[EngineLine]:
        with self.lock:
            self._ensure_started()
            process = self.process
            if process is None or process.stdin is None or process.stdout is None:
                raise StockfishRuntimeError("Unable to communicate with Stockfish.")

            try:
                self._drain_output()
                self._send(process, f"setoption name MultiPV value {multipv}")
                self._send(process, "isready")
                self._wait_for("readyok")
                self._send(process, f"position fen {fen}")
                if movetime_ms is not None:
                    self._send(process, f"go movetime {movetime_ms}")
                else:
                    self._send(process, f"go depth {depth}")
                lines = self._collect_analysis()
            except Exception:
                self._restart()
                raise

        return _parse_engine_lines(lines)

    def _ensure_started(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return

        process = subprocess.Popen(
            [str(self.executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        if process.stdin is None or process.stdout is None:
            raise StockfishRuntimeError("Unable to communicate with Stockfish.")

        self.process = process
        self.output = queue.Queue()
        reader = threading.Thread(target=self._read_stdout, args=(process.stdout, self.output), daemon=True)
        reader.start()
        self.reader = reader

        self._send(process, "uci")
        self._wait_for("uciok")
        self._send(process, "isready")
        self._wait_for("readyok")
        self._send(process, "ucinewgame")
        self._send(process, "isready")
        self._wait_for("readyok")

    def _restart(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return
        self._send(process, "quit", ignore_broken_pipe=True)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()

    def _drain_output(self) -> None:
        while True:
            try:
                self.output.get_nowait()
            except queue.Empty:
                return

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

    def _wait_for(self, expected: str) -> None:
        deadline = threading.Event()
        timer = threading.Timer(self.timeout_seconds, deadline.set)
        timer.start()
        try:
            while not deadline.is_set():
                try:
                    line = self.output.get(timeout=0.05)
                except queue.Empty:
                    continue
                if line == expected:
                    return
        finally:
            timer.cancel()
        raise StockfishRuntimeError(f"Timed out waiting for Stockfish response: {expected}")

    def _collect_analysis(self) -> list[str]:
        collected: list[str] = []
        deadline = threading.Event()
        timer = threading.Timer(self.timeout_seconds, deadline.set)
        timer.start()
        try:
            while not deadline.is_set():
                try:
                    line = self.output.get(timeout=0.05)
                except queue.Empty:
                    continue
                collected.append(line)
                if line.startswith("bestmove"):
                    return collected
        finally:
            timer.cancel()
        raise StockfishRuntimeError("Timed out while Stockfish was analyzing the position.")


def _get_persistent_process(executable: Path, timeout_seconds: float) -> _PersistentStockfishProcess:
    key = str(executable)
    with _processes_lock:
        process = _persistent_processes.get(key)
        if process is None:
            process = _PersistentStockfishProcess(executable, timeout_seconds)
            _persistent_processes[key] = process
        return process


def _claim_inflight_analysis(key: tuple[str, str, int, int, int | None]) -> tuple[_InflightSlot, bool]:
    with _inflight_lock:
        slot = _inflight_analyses.get(key)
        if slot is not None:
            return slot, False
        slot = _InflightSlot()
        _inflight_analyses[key] = slot
        return slot, True


def _wait_for_inflight_analysis(key: tuple[str, str, int, int, int | None], slot: _InflightSlot, timeout_seconds: float) -> list[EngineLine]:
    if not slot.event.wait(timeout_seconds + 1.0):
        raise StockfishRuntimeError("Timed out waiting for shared Stockfish analysis.")
    if slot.error is not None:
        raise slot.error
    if slot.result is None:
        raise StockfishRuntimeError("Shared Stockfish analysis returned no result.")
    cached = _get_cached_analysis(key)
    return cached if cached is not None else list(slot.result)


def _finish_inflight_analysis(
    key: tuple[str, str, int, int, int | None],
    slot: _InflightSlot,
    result: list[EngineLine] | None,
    error: BaseException | None,
) -> None:
    with _inflight_lock:
        slot.result = list(result) if result is not None else None
        slot.error = error
        _inflight_analyses.pop(key, None)
        slot.event.set()


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


def _get_cached_analysis(key: tuple[str, str, int, int, int | None]) -> list[EngineLine] | None:
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


def _set_cached_analysis(key: tuple[str, str, int, int, int | None], lines: list[EngineLine]) -> None:
    with _analysis_cache_lock:
        if len(_analysis_cache) >= _ANALYSIS_CACHE_MAX_ITEMS:
            oldest_key = min(_analysis_cache, key=lambda item: _analysis_cache[item][0])
            _analysis_cache.pop(oldest_key, None)
        _analysis_cache[key] = (monotonic(), list(lines))
