# Chess Elo Coach Frontend

Next.js App Router frontend for the plan-first chess training interface.

## Setup

```bash
npm install
npm run dev
```

The frontend expects the backend at:

```text
http://localhost:8000
```

Override with:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Scripts

- `npm run dev`
- `npm run build`
- `npm run build:live-server`
- `npm run lint`
- `npm run test`

## Visual Studio Code Live Server

Live Server cannot run Next.js source files directly. Build the static export first:

```bash
npm run build:live-server
```

Then open this folder with Live Server:

```text
frontend/out/
```

The FastAPI backend still needs to run separately on `http://localhost:8000`.

## V4 Interface

The app starts with the main pedagogical choice: play white or play black.

- White: choose an opening plan before starting.
- Black: enter White's first move on the internal board, then choose an adapted black plan.
- Free mode remains available, but it is secondary.

The default UI is plan-first:

- the selected opening stays locked for the game,
- Stockfish candidates stay in advanced technical details,
- history, glossary and technical details live in the corner menu,
- move cards explain the idea directly,
- complexity labels replace the visible Elo selector.

## Vercel

Import the GitHub repo in Vercel with `frontend/` as the root directory.

Set this environment variable in Vercel once the backend is deployed:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain
```
