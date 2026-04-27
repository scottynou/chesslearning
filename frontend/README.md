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

## V3 Interface

The app is now split into two simple states:

- opening gallery: choose a guided plan,
- coach view: board plus one plan-first coaching panel.

The default UI is beginner-first:

- visible levels are Beginner, Intermediate and Pro,
- the selected opening stays locked for the game,
- Stockfish candidates stay in technical details,
- last-move review is requested by clicking a button,
- SAN, UCI, cp and PV remain hidden in advanced sections.

## Vercel

Set this environment variable in Vercel once the backend is deployed:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain
```
