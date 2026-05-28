from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_winrate_data(monkeypatch, tmp_path):
    """
    Isole la suite de tests des fichiers Lichess de production
    (app/data/lichess_winrates.sqlite et lichess_winrate_model.json).

    Sans ca, les tests qui verifient les tiers stockfish/fallback du
    winrate_service tomberaient sur la vraie base et renverraient
    'lichess_exact'/'lichess_model'. On pointe les env vars vers des chemins
    inexistants : resolve_existing_path renvoie alors None et le service
    suit la cascade attendue. Les tests qui passent explicitement un db_path
    (base temporaire) continuent de fonctionner normalement.
    """
    monkeypatch.setenv("LICHESS_WINRATE_DB", str(tmp_path / "no_lichess_db.sqlite"))
    monkeypatch.setenv("LICHESS_WINRATE_MODEL_PATH", str(tmp_path / "no_lichess_model.json"))
