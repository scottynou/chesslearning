from __future__ import annotations

import os
import shutil

import chess
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .bot_service import choose_bot_move
from .cache import MemoryCache
from .elo_ranker import rank_candidates
from .explanation_service import explain_candidate, explain_move
from .opening_coach import build_position_plan
from .review_service import review_move
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AvailablePlansResponse,
    BotMoveRequest,
    BotMoveResponse,
    ExplainCandidateRequest,
    ExplainCandidateResponse,
    ExplainRequest,
    ExplainResponse,
    PositionPlanRequest,
    PositionPlanResponse,
    PlanRecommendationsRequest,
    PlanRecommendationsResponse,
    ReviewMoveRequest,
    ReviewMoveResponse,
)
from .stockfish_engine import StockfishConfigurationError, StockfishEngine, StockfishRuntimeError
from .strategy.opening_coach import list_available_plans
from .strategy.plan_engine import get_plan_recommendations

load_dotenv()

app = FastAPI(title="Chess Elo Coach API", version="0.1.0")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://127.0.0.1:3000"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

analyze_cache: MemoryCache[AnalyzeResponse] = MemoryCache(ttl_seconds=300)
explain_cache: MemoryCache[ExplainResponse] = MemoryCache(ttl_seconds=900)
explain_candidate_cache: MemoryCache[ExplainCandidateResponse] = MemoryCache(ttl_seconds=900)
review_cache: MemoryCache[ReviewMoveResponse] = MemoryCache(ttl_seconds=900)
plan_cache: MemoryCache[PositionPlanResponse] = MemoryCache(ttl_seconds=300)
plan_recommendations_cache: MemoryCache[PlanRecommendationsResponse] = MemoryCache(ttl_seconds=300)


@app.get("/health")
def health() -> dict[str, bool | str]:
    stockfish_configured = bool(os.getenv("STOCKFISH_PATH") or shutil.which("stockfish") or os.path.exists("/usr/games/stockfish") or os.path.exists("/usr/bin/stockfish"))
    return {
        "ok": True,
        "stockfishConfigured": stockfish_configured,
        "aiProvider": os.getenv("AI_PROVIDER", "heuristic"),
        "openaiConfigured": bool(os.getenv("OPENAI_API_KEY")),
        "geminiConfigured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    cache_key = f"{request.fen}|{request.elo}|{request.max_moves}|{request.engine_depth}"
    cached = analyze_cache.get(cache_key)
    if cached is not None:
        return cached

    board = chess.Board(request.fen)
    multipv = min(30, request.max_moves * 3)

    try:
        engine_lines = StockfishEngine().analyze(
            fen=request.fen,
            multipv=multipv,
            depth=request.engine_depth,
        )
    except StockfishConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StockfishRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    candidates = rank_candidates(
        fen=request.fen,
        lines=engine_lines,
        elo=request.elo,
        max_moves=request.max_moves,
    )
    response = AnalyzeResponse(
        fen=request.fen,
        elo=request.elo,
        sideToMove="white" if board.turn == chess.WHITE else "black",
        candidates=candidates,
    )
    analyze_cache.set(cache_key, response)
    return response


@app.post("/explain", response_model=ExplainResponse)
def explain(request: ExplainRequest) -> ExplainResponse:
    cache_key = f"{request.fen}|{request.elo}|{request.selected_move.move_uci}"
    cached = explain_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = explain_move(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to generate explanation: {exc}") from exc

    explain_cache.set(cache_key, response)
    return response


@app.post("/explain-candidate", response_model=ExplainCandidateResponse)
def explain_candidate_endpoint(request: ExplainCandidateRequest) -> ExplainCandidateResponse:
    cache_key = f"{request.fen}|{request.elo}|{request.selected_move.move_uci}|{request.beginner_mode}|{os.getenv('AI_PROVIDER', 'heuristic')}"
    cached = explain_candidate_cache.get(cache_key)
    if cached is not None:
        return cached

    response = explain_candidate(request)
    explain_candidate_cache.set(cache_key, response)
    return response


@app.post("/review-move", response_model=ReviewMoveResponse)
def review_move_endpoint(request: ReviewMoveRequest) -> ReviewMoveResponse:
    cache_key = f"{request.fen_before}|{request.fen_after}|{request.move_uci}|{request.elo}"
    cached = review_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = review_move(request)
    except StockfishConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StockfishRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    review_cache.set(cache_key, response)
    return response


@app.post("/bot-move", response_model=BotMoveResponse)
def bot_move_endpoint(request: BotMoveRequest) -> BotMoveResponse:
    try:
        return choose_bot_move(request)
    except StockfishConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StockfishRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/position-plan", response_model=PositionPlanResponse)
def position_plan_endpoint(request: PositionPlanRequest) -> PositionPlanResponse:
    cache_key = f"{request.fen}|{','.join(request.move_history_uci)}"
    cached = plan_cache.get(cache_key)
    if cached is not None:
        return cached

    response = PositionPlanResponse.model_validate(
        build_position_plan(request.fen, request.move_history_uci)
    )
    plan_cache.set(cache_key, response)
    return response


@app.get("/available-plans", response_model=AvailablePlansResponse)
def available_plans(side: str | None = None, elo: int | None = None, includeHidden: bool = False) -> AvailablePlansResponse:
    return AvailablePlansResponse(plans=list_available_plans(side=side, elo=elo, include_hidden=includeHidden))


@app.post("/plan-recommendations", response_model=PlanRecommendationsResponse)
def plan_recommendations_endpoint(request: PlanRecommendationsRequest) -> PlanRecommendationsResponse:
    cache_key = f"{request.fen}|{request.selected_plan_id}|{request.elo}|{request.skill_level}|{request.max_moves}|{request.engine_depth}|{','.join(request.move_history_uci)}"
    cached = plan_recommendations_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        response = PlanRecommendationsResponse.model_validate(
            get_plan_recommendations(
                fen=request.fen,
                selected_plan_id=request.selected_plan_id,
                elo=request.elo,
                skill_level=request.skill_level,
                move_history=request.move_history_uci,
                max_moves=request.max_moves,
                engine_depth=request.engine_depth,
            )
        )
    except StockfishConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StockfishRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    plan_recommendations_cache.set(cache_key, response)
    return response
