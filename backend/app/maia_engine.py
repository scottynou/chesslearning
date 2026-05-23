"""
Client UCI pour lc0 charge avec les poids Maia.

Maia est un reseau de neurones entraine specifiquement sur les parties
humaines a un Elo cible (1100, 1500, 1900). Au lieu de chercher le
meilleur coup, il retourne la probabilite que chaque coup soit joue par
un humain de ce niveau.

Implementation defensive : si lc0 ou les poids ne sont pas presents,
is_available() retourne False et tout le module se desactive sans erreur.
Le systeme retombe alors sur l'humanisation heuristique existante.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MaiaMove:
    move_uci: str
    probability: float


_DEFAULT_LEVEL = 1500
_SUPPORTED_LEVELS = (1100, 1500, 1900)
_engines_lock = threading.Lock()
_engines: dict[int, "MaiaEngine"] = {}


def get_engine(level: int = _DEFAULT_LEVEL) -> "MaiaEngine":
    """Singleton par niveau, evite de recreer un process lc0 a chaque coup."""
    target = level if level in _SUPPORTED_LEVELS else _closest_supported(level)
    with _engines_lock:
        if target not in _engines:
            _engines[target] = MaiaEngine(weight_level=target)
        return _engines[target]


def is_enabled() -> bool:
    if os.getenv("MAIA_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return False
    return get_engine().is_available()


def _closest_supported(level: int) -> int:
    return min(_SUPPORTED_LEVELS, key=lambda x: abs(x - level))


class MaiaEngine:
    def __init__(self, weight_level: int = _DEFAULT_LEVEL, timeout_seconds: float = 8.0):
        self.weight_level = weight_level
        self.timeout_seconds = timeout_seconds
        self.lc0_path = os.getenv("LC0_PATH", "/opt/lc0/lc0")
        weights_dir = os.getenv("MAIA_WEIGHTS_DIR", "/opt/maia-weights")
        self.weights_path = Path(weights_dir) / f"maia-{weight_level}.pb.gz"
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._available_cache: bool | None = None

    def is_available(self) -> bool:
        if self._available_cache is not None:
            return self._available_cache
        lc0 = Path(self.lc0_path)
        ok = lc0.is_file() and os.access(lc0, os.X_OK) and self.weights_path.is_file()
        self._available_cache = ok
        if not ok:
            logger.info(
                "Maia indisponible (lc0=%s exists=%s, weights=%s exists=%s)",
                self.lc0_path,
                lc0.is_file(),
                self.weights_path,
                self.weights_path.is_file(),
            )
        return ok

    def suggest(self, fen: str, top_n: int = 12) -> list[MaiaMove]:
        if not self.is_available():
            return []
        try:
            with self._lock:
                process = self._ensure_process()
                self._send(process, f"position fen {fen}")
                self._send(process, "go nodes 1")
                results, raw = self._read_policy(process, top_n)
                if not results and raw:
                    logger.warning("Maia raw lines (no parse): %s", raw[:1500])
                return results
        except Exception as exc:  # noqa: BLE001
            logger.warning("Maia suggest failed: %s", exc)
            self._close_process()
            return []

    def suggest_with_raw(self, fen: str, top_n: int = 12) -> tuple[list[MaiaMove], str]:
        """Variante diagnostique : renvoie aussi le raw stdout pour debug."""
        if not self.is_available():
            return [], ""
        try:
            with self._lock:
                process = self._ensure_process()
                self._send(process, f"position fen {fen}")
                self._send(process, "go nodes 1")
                return self._read_policy(process, top_n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Maia suggest failed: %s", exc)
            self._close_process()
            return [], f"error: {exc}"

    def shutdown(self) -> None:
        with self._lock:
            self._close_process()

    def _ensure_process(self) -> subprocess.Popen[bytes]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        # stderr=DEVNULL pour eviter que le buffer ne se remplisse et bloque
        # lc0 (on ne lit pas activement stderr dans le process persistent).
        self._process = subprocess.Popen(
            [self.lc0_path, f"--weights={self.weights_path}"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._send(self._process, "uci")
        self._wait_for(self._process, b"uciok")
        # Active la sortie des probas pour tous les coups (clef de l'humanisation Maia).
        # NB : doit etre envoye AVANT isready/ucinewgame pour etre pris en compte.
        self._send(self._process, "setoption name VerboseMoveStats value true")
        self._send(self._process, "isready")
        self._wait_for(self._process, b"readyok")
        return self._process

    def _send(self, process: subprocess.Popen[bytes], command: str) -> None:
        assert process.stdin is not None
        process.stdin.write((command + "\n").encode("utf-8"))
        process.stdin.flush()

    def _wait_for(self, process: subprocess.Popen[bytes], token: bytes) -> None:
        assert process.stdout is not None
        deadline = monotonic() + self.timeout_seconds
        while monotonic() < deadline:
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("Maia process closed unexpectedly")
            if token in line:
                return
        raise TimeoutError(f"Maia timeout waiting for {token!r}")

    def _read_policy(self, process: subprocess.Popen[bytes], top_n: int) -> tuple[list[MaiaMove], str]:
        assert process.stdout is not None
        results: list[MaiaMove] = []
        raw_lines: list[str] = []
        deadline = monotonic() + self.timeout_seconds
        while monotonic() < deadline:
            line = process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="ignore").strip()
            raw_lines.append(decoded)
            if decoded.startswith("info string"):
                parsed = _parse_policy_line(decoded)
                if parsed is not None:
                    results.append(parsed)
            elif decoded.startswith("bestmove"):
                break
        results.sort(key=lambda move: -move.probability)
        return results[:top_n], "\n".join(raw_lines)

    def _close_process(self) -> None:
        if self._process is None:
            return
        try:
            if self._process.poll() is None:
                self._send(self._process, "quit")
                self._process.wait(timeout=2.0)
        except Exception:  # noqa: BLE001
            try:
                self._process.kill()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._process = None


def _parse_policy_line(line: str) -> MaiaMove | None:
    """
    Parse une ligne 'info string ... (P: X.YZ%) ...' en cherchant un coup UCI
    quelque part dans la ligne. Robuste a la variation de format entre versions
    de lc0 (v0.30 : 'info string e2e4 ...', v0.31+ : 'info string node PV: e2e4 ...').
    """
    pct_index = line.find("P:")
    if pct_index == -1:
        return None
    # Cherche le premier token UCI-like dans toute la ligne.
    move_uci: str | None = None
    for token in line.split():
        clean = token.strip("()[],.")
        if _looks_like_uci(clean):
            move_uci = clean
            break
    if move_uci is None:
        return None
    tail = line[pct_index + 2 :].strip()
    pct_token = tail.split("%", 1)[0].strip()
    try:
        probability = float(pct_token) / 100.0
    except ValueError:
        return None
    return MaiaMove(move_uci=move_uci, probability=probability)


def _looks_like_uci(token: str) -> bool:
    if len(token) not in {4, 5}:
        return False
    files = "abcdefgh"
    ranks = "12345678"
    return (
        token[0] in files
        and token[1] in ranks
        and token[2] in files
        and token[3] in ranks
        and (len(token) == 4 or token[4] in "qrbn")
    )
