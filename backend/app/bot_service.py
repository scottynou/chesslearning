from __future__ import annotations

from .elo_ranker import rank_candidates
from .schemas import BotMoveRequest, BotMoveResponse
from .stockfish_engine import StockfishEngine


def choose_bot_move(request: BotMoveRequest) -> BotMoveResponse:
    lines = StockfishEngine().analyze(
        request.fen,
        multipv=1,
        depth=max(request.engine_depth, 14),
    )
    candidates = rank_candidates(request.fen, lines, elo=3200, max_moves=1)
    if not candidates:
        raise RuntimeError("No legal bot move available.")

    selected = candidates[0]
    return BotMoveResponse(
        move=selected,
        selectionReason="Meilleur coup Stockfish disponible.",
        updatedStrategyState=request.strategy_state or {},
        explanationPreview=selected.summary,
    )
