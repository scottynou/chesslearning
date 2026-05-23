from __future__ import annotations

import logging
import os
import re
import shutil
import time
import hashlib
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
from .image_import_service import ImageImportProviderError, import_position_image
from .live_plan_service import live_plan_insight
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
    ImportPositionImageRequest,
    ImportPositionImageResponse,
    LivePlanInsightRequest,
    LivePlanInsightResponse,
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
from .maia_engine import get_engine as get_maia_engine, is_enabled as maia_is_enabled

load_dotenv()

app = FastAPI(title="Chess Learning API", version="0.1.0")


@app.on_event("startup")
def warm_engines() -> None:
    """Lance lc0+Maia et un coup Stockfish des le boot pour eviter le cold
    start du premier utilisateur. Sans bloquer le boot du serveur si l'un
    des deux echoue."""
    import threading

    def _warm():
        try:
            if maia_is_enabled():
                # Force le boot du process lc0 + une suggest pour mettre en cache.
                engine = get_maia_engine(1500)
                engine.suggest("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", top_n=3)
                logger.info("Maia warmed up")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Maia warmup failed: %s", exc)
        try:
            StockfishEngine().analyze(
                "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                multipv=3,
                depth=8,
                movetime_ms=200,
            )
            logger.info("Stockfish warmed up")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stockfish warmup failed: %s", exc)

    threading.Thread(target=_warm, daemon=True).start()
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

EXPENSIVE_PATHS = {"/analyze", "/plan-recommendations", "/bot-move", "/review-move", "/explain-candidate", "/live-plan-insight", "/import-position-image"}
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

# Caches : TTL augmente sur les positions d'analyse (deterministes) pour
# tirer parti des positions communes (ouvertures jouees par beaucoup d'users).
analyze_cache: MemoryCache[AnalyzeResponse] = MemoryCache(ttl_seconds=1800)
explain_cache: MemoryCache[ExplainResponse] = MemoryCache(ttl_seconds=1800)
explain_candidate_cache: MemoryCache[ExplainCandidateResponse] = MemoryCache(ttl_seconds=1800)
review_cache: MemoryCache[ReviewMoveResponse] = MemoryCache(ttl_seconds=1800)
plan_cache: MemoryCache[PositionPlanResponse] = MemoryCache(ttl_seconds=900)
plan_recommendations_cache: MemoryCache[PlanRecommendationsResponse] = MemoryCache(ttl_seconds=900)
live_plan_insight_cache: MemoryCache[LivePlanInsightResponse] = MemoryCache(ttl_seconds=1800)
bot_move_cache: MemoryCache[BotMoveResponse] = MemoryCache(ttl_seconds=300)
image_import_cache: MemoryCache[ImportPositionImageResponse] = MemoryCache(ttl_seconds=3600)


@app.get("/health")
def health() -> dict[str, bool | str]:
    from .maia_engine import get_engine as get_maia_engine, is_enabled as maia_is_enabled
    stockfish_configured = bool(os.getenv("STOCKFISH_PATH") or shutil.which("stockfish") or os.path.exists("/usr/games/stockfish") or os.path.exists("/usr/bin/stockfish"))
    lc0_path = os.getenv("LC0_PATH", "/opt/lc0/lc0")
    weights_dir = os.getenv("MAIA_WEIGHTS_DIR", "/opt/maia-weights")
    return {
        "ok": True,
        "stockfishConfigured": stockfish_configured,
        "aiProvider": configured_provider_name(),
        "aiProviderMode": os.getenv("AI_PROVIDER", "auto"),
        "aiRerankProvider": os.getenv("AI_RERANK_PROVIDER", "gemini"),
        "aiRerankModel": os.getenv("AI_RERANK_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        "imageImportModel": os.getenv("IMAGE_IMPORT_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        "openaiConfigured": bool(os.getenv("OPENAI_API_KEY")),
        "geminiConfigured": bool(os.getenv("GEMINI_API_KEY")),
        "maiaEnabled": maia_is_enabled(),
        "maiaLc0Present": os.path.isfile(lc0_path) and os.access(lc0_path, os.X_OK),
        "maiaWeights1500": os.path.isfile(f"{weights_dir}/maia-1500.pb.gz"),
        "maiaWeights1900": os.path.isfile(f"{weights_dir}/maia-1900.pb.gz"),
    }


@app.get("/debug/maia-suggest")
def debug_maia_suggest() -> dict[str, object]:
    """Appelle MaiaEngine.suggest_with_raw pour voir le format brut de lc0."""
    from .maia_engine import get_engine
    try:
        engine = get_engine(1500)
        suggestions, raw = engine.suggest_with_raw("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", top_n=10)
        return {
            "ok": True,
            "available": engine.is_available(),
            "count": len(suggestions),
            "moves": [{"uci": m.move_uci, "prob": m.probability} for m in suggestions],
            "raw": raw[:3000],
        }
    except Exception as exc:  # noqa: BLE001
        import traceback
        return {"ok": False, "error": str(exc), "trace": traceback.format_exc()[:2000]}


@app.get("/debug/maia-test")
def debug_maia_test() -> dict[str, object]:
    """Lance lc0 et execute une analyse pour capturer le format exact des coups."""
    import subprocess
    lc0_path = os.getenv("LC0_PATH", "/opt/lc0/lc0")
    weights = f"{os.getenv('MAIA_WEIGHTS_DIR', '/opt/maia-weights')}/maia-1500.pb.gz"
    if not os.path.isfile(lc0_path):
        return {"ok": False, "error": "lc0 binary missing"}
    try:
        cmds = b"uci\nsetoption name VerboseMoveStats value true\nisready\nposition startpos moves e2e4\ngo nodes 1\nquit\n"
        result = subprocess.run(
            [lc0_path, f"--weights={weights}"],
            input=cmds,
            capture_output=True,
            timeout=30,
        )
        out = result.stdout.decode("utf-8", errors="ignore")
        # Garde uniquement les lignes apres "readyok" pour voir la sortie de go.
        post_ready = out.split("readyok", 1)[-1]
        return {
            "ok": True,
            "returncode": result.returncode,
            "lengthTotal": len(out),
            "postReadyok": post_ready[:5000],
            "stderr": result.stderr.decode("utf-8", errors="ignore")[:500],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": "timeout",
            "stdout": (exc.stdout or b"").decode("utf-8", errors="ignore")[-4000:],
            "stderr": (exc.stderr or b"").decode("utf-8", errors="ignore")[:500],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


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


@app.post("/live-plan-insight", response_model=LivePlanInsightResponse)
def live_plan_insight_endpoint(request: LivePlanInsightRequest) -> LivePlanInsightResponse:
    cache_key = (
        f"{request.fen}|{request.selected_plan_id}|{','.join(request.move_history_uci)}|"
        f"{request.phase}|{request.opening_state}|{configured_provider_name()}"
    )
    cached = live_plan_insight_cache.get(cache_key)
    if cached is not None:
        return cached

    response = live_plan_insight(request)
    live_plan_insight_cache.set(cache_key, response)
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


@app.post("/import-position-image", response_model=ImportPositionImageResponse)
def import_position_image_endpoint(request: ImportPositionImageRequest) -> ImportPositionImageResponse:
    image_hash = hashlib.sha256(request.model_dump_json(by_alias=True).encode("utf-8")).hexdigest()
    import_model = os.getenv("IMAGE_IMPORT_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    cache_key = f"{request.mime_type}|{image_hash}|{import_model}"
    cached = image_import_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = import_position_image(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Impossible de lire une position d'echecs valide sur cette image.") from exc
    except ImageImportProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Import image indisponible: {type(exc).__name__}") from exc

    image_import_cache.set(cache_key, response)
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
    cache_key = (
        f"{request.fen}|{request.selected_plan_id}|{request.user_side}|{request.elo}|{request.skill_level}|{request.human_profile}|{request.coach_style}|{request.max_moves}|"
        f"{request.engine_depth}|{','.join(request.move_history_uci)}|{os.getenv('AI_RERANK_PROVIDER', 'gemini')}|"
        f"{os.getenv('AI_RERANK_MODEL') or os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')}"
    )
    cached = plan_recommendations_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        response = PlanRecommendationsResponse.model_validate(
            get_plan_recommendations(
                fen=request.fen,
                selected_plan_id=request.selected_plan_id,
                user_side=request.user_side,
                elo=request.elo,
                skill_level=request.skill_level,
                human_profile=request.human_profile,
                coach_style=request.coach_style,
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
