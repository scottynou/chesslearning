# Chess Learning

Chess Learning is a plan-first chess training web app. It uses an internal board only: it does not read live games from Chess.com, Lichess, or any other site, and it never plays moves automatically outside its own training board.

## Project Layout

```text
chess-elo-coach/
  frontend/   Next.js App Router, React, TypeScript, Tailwind CSS
  backend/    FastAPI, Stockfish UCI, plan-first coaching, explanations
  tools/      Local Stockfish binary in this workspace
```

## Requirements

- Node.js 20+
- Python 3.11+
- A Stockfish executable

## Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set:

```env
STOCKFISH_PATH=C:\path\to\stockfish.exe
```

This workspace already includes a local Stockfish 18 Windows binary at:

```text
tools/stockfish/stockfish/stockfish-windows-x86-64.exe
```

The generated `backend/.env` points to it.

Run the API:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run backend tests:

```bash
pytest
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

If your backend is not on `http://localhost:8000`, create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Opening With VS Code Live Server

Live Server can serve the static frontend export, but it cannot compile Next.js or start the FastAPI backend.

```bash
cd frontend
npm run build:live-server
```

Then use Live Server on:

```text
frontend/out/
```

Keep the backend running separately:

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Current V4 Features

- The app starts with a clear choice: play White, play Black, or use free mode.
- White chooses an opening plan before the game starts.
- Black enters White's first move first, then receives adapted black plans.
- The selected plan stays locked for the game; deviations adapt the next move instead of replacing the plan.
- The main UI shows one recommended plan move plus adapted alternatives only when useful.
- Engine candidates are kept in advanced technical details, not in the primary learning flow.
- Last-move review is on demand instead of automatic.
- Plan recommendations include progress, opening success criteria, phase status and a coach message.
- Beginner-first move labels show the piece name, origin square and target square instead of raw `Nf6` or `g8f6`.
- Human evaluation labels such as `Leger avantage noir` replace raw `-31 cp` in beginner mode.
- Raw SAN/UCI/cp/PV details stay inside advanced technical sections.
- `GET /available-plans` exposes the beginner repertoire.
- `POST /plan-recommendations` returns the enriched plan-first coach response.
- `POST /review-move` explains the last played move and compares it with the best recommendation.
- `POST /bot-move` powers the internal bot for "only white" and "only black" modes.
- A glossary explains FEN, PGN, Elo, cp, SAN, UCI, castling, en passant, opening, middlegame, and endgame.
- The app still uses only its own internal board. It does not read Chess.com/Lichess and does not autoplay externally.

## Public Deployment

Chosen simple setup:

- Frontend: Render Static Site from `frontend/`.
- Backend: Render Web Service using `backend/Dockerfile`.
- Stockfish: installed inside the backend Docker image.
- AI: keep `AI_PROVIDER=heuristic` for the public MVP to avoid API costs.

Follow the exact deployment runbook in [`DEPLOYMENT.md`](DEPLOYMENT.md).

Frontend production env:

```env
NEXT_PUBLIC_API_BASE_URL=<automatically set from the backend RENDER_EXTERNAL_URL in render.yaml>
```

Backend production env:

```env
STOCKFISH_PATH=/usr/games/stockfish
FRONTEND_ORIGIN=https://chess-elo-coach-web.onrender.com
FRONTEND_ORIGIN_REGEX=https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.onrender\.com
AI_PROVIDER=heuristic
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_PER_WINDOW=45
```

`render.yaml` creates both Render services. The frontend reads the backend public URL from Render's `RENDER_EXTERNAL_URL`, so random Blueprint suffixes are handled automatically.

## API Overview

- `POST /analyze`: Stockfish candidates with Elo-aware ranking.
- `POST /explain`: legacy explanation endpoint.
- `POST /explain-candidate`: beginner-first explanation for a selected candidate.
- `POST /review-move`: review of a manually played move.
- `POST /bot-move`: internal bot move for the app board.
- `POST /position-plan`: lightweight phase/strategy panel.
- `GET /available-plans`: available opening plans.
- `POST /plan-recommendations`: plan-first recommendations.
- `GET /health`: backend status.

## AI Providers

Set AI options in `backend/.env`:

```env
AI_PROVIDER=heuristic
AI_VERIFIER_PROVIDER=heuristic
AI_SIMPLIFIER_PROVIDER=none
AI_TIMEOUT_SECONDS=18
```

Supported `AI_PROVIDER` values:

- `heuristic`: local fallback, no API call.
- `openai`: uses `OPENAI_API_KEY` and `OPENAI_MODEL`.
- `gemini`: uses `GEMINI_API_KEY` and `GEMINI_MODEL`.
- `ollama`: uses local `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

Stockfish chooses and analyzes moves. Opening plans structure the training goal. AI providers only explain selected moves. The frontend never receives API keys and never calls AI providers directly.

## Sources Pedagogiques Et Donnees

- FIDE Laws of Chess 2023: official rules reference for legal chess behavior: <https://handbook.fide.com/chapter/E012023>.
- Stockfish: engine analysis and tactical safety gate: <https://stockfishchess.org/>.
- `lichess-org/chess-openings`: future structured source for opening names, ECO and PGN/UCI data: <https://github.com/lichess-org/chess-openings>.
- ECO codes: classification of opening families.
- Lichess Open Database: optional future source for popularity/statistical training data: <https://database.lichess.org/>.
- Syzygy tablebases through `python-chess`: optional future source for exact endgame results up to 7 pieces: <https://python-chess.readthedocs.io/en/latest/syzygy.html>.
- Maia/Maia-2: optional future source for human-likelihood by Elo: <https://maiachess.com/>.

The project must not scrape Chess.com. Videos or informal material can inspire pedagogy, but structured code/data should rely on verifiable sources.

## MVP Limits

- Stockfish must be installed locally for real analysis.
- The human-likelihood model is heuristic, not Maia/Maia-2.
- Opening transposition detection is intentionally simple in V2.
- Syzygy tablebases are documented as a future option; current endgame coaching uses Stockfish plus heuristics.
- AI providers are optional and only used for explanations, never for selecting moves.
- The app is for training on its own board, not for live-game assistance.

## Roadmap

### V0

- Internal board
- Legal moves
- Stockfish analysis
- Top 10 recommendations
- Elo slider
- Heuristic explanations

### V1

- Multi-provider AI explanations
- More robust cache
- Better mobile polish

### V2

- Plan-first coach
- Opening selection
- Plan moves before engine moves
- Adaptation to opponent deviations
- Opening/middlegame/endgame guidance
- Last-move review linked to the plan
- Internal bot linked to the plan
- Verified beginner explanations

### V3

- Simple two-state UI: opening gallery, then plan coach
- Locked selected plan with deviation adaptation
- Internal pedagogical level instead of a visible Elo slider
- Last-move review on demand
- Docker backend with Stockfish for public hosting

### V4

- White/Black first onboarding
- Opening plans filtered after White's first move when playing Black
- Minimal opening cards with expanded details on demand
- Automatic arrow/highlight for the next recommended plan move

### Future

- Import `lichess-org/chess-openings`
- Better transposition detection
- Popularity statistics from structured databases
- Maia/Maia-2 for human-likelihood by Elo
- PGN import/export
- Full-game analysis

### V5

- Local Syzygy tablebases
- Targeted exercises by plan
- Post-game summary: plan adherence, deviations, recurring mistakes and openings to revisit

### V6

- Installable PWA
- Optional user accounts
- Personal training history
- Custom plans
