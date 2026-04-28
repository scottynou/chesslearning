from __future__ import annotations

import logging
import os
import re
import shutil
import time
from collections import defaultdict, deque

import chess
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from .bot_service import choose_bot_move
from .ai_providers.selection import configured_provider_name
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

app = FastAPI(title="Chess Learning API", version="0.1.0")
logger = logging.getLogger(__name__)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
frontend_origins = sorted(
    {
        frontend_origin,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://chess-elo-coach-web-bh95.onrender.com",
        *[origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "").split(",") if origin.strip()],
    }
)
frontend_origin_regex = os.getenv(
    "FRONTEND_ORIGIN_REGEX",
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.(onrender\.com|web\.app|firebaseapp\.com)",
)
try:
    frontend_origin_pattern = re.compile(frontend_origin_regex)
except re.error:
    logger.exception("Invalid FRONTEND_ORIGIN_REGEX, falling back to explicit origins only.")
    frontend_origin_pattern = re.compile(r"$^")


def _origin_is_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    return origin in frontend_origins or bool(frontend_origin_pattern.fullmatch(origin))


def _with_cors_headers(response: Response, origin: str | None) -> Response:
    if not _origin_is_allowed(origin):
        return response
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Vary"] = "Origin"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_origin_regex=frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXPENSIVE_PATHS = {"/analyze", "/plan-recommendations", "/bot-move", "/review-move", "/explain-candidate"}
JSON_BODY_PATHS = EXPENSIVE_PATHS | {"/position-plan", "/explain"}
rate_limit_window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
rate_limit_per_window = int(os.getenv("RATE_LIMIT_PER_WINDOW", "45"))
rate_limit_hits: defaultdict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def simple_ip_rate_limit(request: Request, call_next):
    if request.method == "POST" and request.url.path in EXPENSIVE_PATHS:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "unknown")
        key = f"{client_ip}:{request.url.path}"
        now = time.monotonic()
        hits = rate_limit_hits[key]
        while hits and now - hits[0] > rate_limit_window_seconds:
            hits.popleft()
        if len(hits) >= rate_limit_per_window:
            return JSONResponse(
                status_code=429,
                content={"detail": "Trop de requetes. Attends un instant puis reessaie."},
            )
        hits.append(now)
    return await call_next(request)


@app.middleware("http")
async def cors_error_guard(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled API error on %s %s", request.method, request.url.path)
        response = JSONResponse(status_code=500, content={"detail": "Erreur serveur interne."})
    return _with_cors_headers(response, request.headers.get("origin"))


@app.middleware("http")
async def text_json_body_compat(request: Request, call_next):
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if request.method == "POST" and request.url.path in JSON_BODY_PATHS and content_type == "text/plain":
        # The frontend sends simple text/plain POSTs to avoid browser preflight failures on Render.
        request.scope["headers"] = [
            (key, b"application/json" if key == b"content-type" else value)
            for key, value in request.scope["headers"]
        ]
    return await call_next(request)

analyze_cache: MemoryCache[AnalyzeResponse] = MemoryCache(ttl_seconds=300)
explain_cache: MemoryCache[ExplainResponse] = MemoryCache(ttl_seconds=900)
explain_candidate_cache: MemoryCache[ExplainCandidateResponse] = MemoryCache(ttl_seconds=900)
review_cache: MemoryCache[ReviewMoveResponse] = MemoryCache(ttl_seconds=900)
plan_cache: MemoryCache[PositionPlanResponse] = MemoryCache(ttl_seconds=300)
plan_recommendations_cache: MemoryCache[PlanRecommendationsResponse] = MemoryCache(ttl_seconds=300)
bot_move_cache: MemoryCache[BotMoveResponse] = MemoryCache(ttl_seconds=120)


@app.get("/health")
def health() -> dict[str, bool | str]:
    stockfish_configured = bool(os.getenv("STOCKFISH_PATH") or shutil.which("stockfish") or os.path.exists("/usr/games/stockfish") or os.path.exists("/usr/bin/stockfish"))
    return {
        "ok": True,
        "stockfishConfigured": stockfish_configured,
        "aiProvider": configured_provider_name(),
        "aiProviderMode": os.getenv("AI_PROVIDER", "auto"),
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
    cache_key = f"{request.fen_before}|{request.fen_after}|{request.move_uci}|{request.elo}|{request.selected_plan_id}|{','.join(request.move_history_uci)}|{os.getenv('AI_PROVIDER', 'heuristic')}"
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
    move_history = (request.strategy_state or {}).get("moveHistoryUci", [])
    cache_key = (
        f"{request.fen}|{request.elo}|{request.skill_level}|{request.max_moves}|{request.engine_depth}|"
        f"{request.bot_style}|{request.selected_bot_plan_id}|{request.user_plan_id}|{','.join(str(move) for move in move_history)}"
    )
    cached = bot_move_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = choose_bot_move(request)
    except StockfishConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StockfishRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    bot_move_cache.set(cache_key, response)
    return response


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
def available_plans(
    side: str | None = None,
    elo: int | None = None,
    includeHidden: bool = False,
    firstMove: str | None = None,
) -> AvailablePlansResponse:
    return AvailablePlansResponse(
        plans=list_available_plans(side=side, elo=elo, include_hidden=includeHidden, first_move=firstMove)
    )


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
