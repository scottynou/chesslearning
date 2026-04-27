# AGENTS.md

## Product Rules

- This is a training app, not a live-game assistant.
- Do not integrate Chess.com or Lichess live games.
- Do not add autoplay or a button that plays recommended moves.
- Keep assistance visible and explicit.
- The user must always move pieces manually.

## Architecture

- Frontend lives in `frontend/`.
- Backend lives in `backend/`.
- Stockfish selects and evaluates moves.
- The Elo-aware ranker reorders engine lines pedagogically.
- OpenAI is optional and only explains already-provided engine/candidate data.

## Implementation Notes

- Prefer small, typed interfaces between frontend and backend.
- Keep mobile layouts first-class.
- Keep explanations in French by default.
- Avoid broad refactors unrelated to the current feature.
