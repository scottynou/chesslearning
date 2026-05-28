# Chess Learning Backend

FastAPI backend for Stockfish analysis, plan-first coaching and pedagogical explanations.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set `STOCKFISH_PATH` to your local Stockfish executable.

In this workspace, Stockfish 18 has been downloaded to:

```text
../tools/stockfish/stockfish/stockfish-windows-x86-64.exe
```

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If `STOCKFISH_PATH` is not set, the backend also checks `stockfish` in PATH, `/usr/games/stockfish`, and `/usr/bin/stockfish`.

## Test

```bash
pytest
```

## API

- `POST /analyze`
- `POST /explain`
- `POST /explain-candidate`
- `POST /review-move`
- `POST /bot-move`
- `POST /position-plan`
- `POST /winrate`
- `GET /available-plans`
- `POST /plan-recommendations`
- `GET /health`

## Winrate Lichess

`POST /winrate` returns one readable number: the chance that the requested side wins from a FEN. It prefers exact aggregated Lichess positions, then an optional local Lichess model, then Stockfish, then a simple local formula. Draws stay in the denominator for Lichess exact stats, so `40 white wins / 30 draws / 30 black wins` returns a 40% white winrate.

Build the exact-position database from streamed Lichess PGN exports:

```bash
python scripts/ingest_lichess_winrates.py lichess_db_standard_rated_YYYY-MM.pgn.zst
```

Optionally train the rare-position model from the aggregate DB:

```bash
python scripts/train_lichess_winrate_model.py
```

Useful env vars:

```env
LICHESS_WINRATE_DB=app/data/lichess_winrates.sqlite
LICHESS_WINRATE_MODEL_PATH=app/data/lichess_winrate_model.json
WINRATE_STOCKFISH_DEPTH=12
WINRATE_STOCKFISH_MOVETIME_MS=350
```

## Plan-First Coaching

The strategy layer lives in `app/strategy/`:

- `opening_coach.py`: loads the beginner repertoire, detects deviations and explains opening status.
- `plan_engine.py`: recalculates the active plan after each move.
- `move_merger.py`: merges plan moves and Stockfish moves with a safety gate.
- `phase_detector.py`: classifies opening, transition, middlegame and endgame.
- `middlegame_coach.py` and `endgame_coach.py`: provide beginner-friendly goals after the opening.

Opening data lives in `app/data/opening_plans/`. The hidden traps file is not shown in the main menu by default.

`POST /plan-recommendations` keeps `selectedPlanId` locked when provided. Detected transpositions are returned as context only; they do not replace the selected plan.

## Docker / Public Hosting

The backend includes a production-oriented Dockerfile:

```bash
docker build -t chess-elo-coach-api .
docker run -p 8000:8000 -e FRONTEND_ORIGIN=http://localhost:3000 chess-elo-coach-api
```

The image installs Stockfish through the Linux package manager and defaults to:

```env
STOCKFISH_PATH=/usr/games/stockfish
AI_PROVIDER=heuristic
```

For Render, use the repository-level `render.yaml`. The default configuration accepts localhost and Render domains through `FRONTEND_ORIGIN_REGEX`.

Public MVP rate limit:

```env
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_PER_WINDOW=45
```

## AI Providers

Default:

```env
AI_PROVIDER=heuristic
```

Optional:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-mini
AI_VERIFIER_PROVIDER=heuristic
AI_SIMPLIFIER_PROVIDER=none
AI_TIMEOUT_SECONDS=18

AI_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash

AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

If an AI provider fails validation or times out, the backend falls back to the heuristic provider.
