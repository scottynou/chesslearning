# Deploiement public sur Render

Chemin choisi maintenant : tout mettre sur Render.

- Frontend : Render Static Site `chess-elo-coach-web`.
- Backend : Render Web Service Docker `chess-elo-coach-api`.
- Stockfish : installe dans l'image Docker backend.
- IA : `AI_PROVIDER=heuristic`, donc aucun cout API.

## Ce que le repo prepare deja

- `render.yaml` cree les deux services Render.
- `backend/Dockerfile` installe Stockfish et lance FastAPI.
- `frontend/next.config.mjs` exporte le site statique dans `frontend/out`.
- Le frontend recupere automatiquement l'URL publique du backend Render avec `RENDER_EXTERNAL_URL`.

- Le backend accepte les domaines Render et Vercel via CORS.
- Les endpoints couteux ont une limite simple par IP.

## Ce que tu dois faire sur Render

Tu es sur l'ecran avec les cartes `Static Sites`, `Web Services`, etc.

Le plus propre :

1. Cherche dans Render l'entree `Blueprint`.
2. Si tu la vois, clique dessus.
3. Choisis le repo GitHub `scottynou/chesslearning`.
4. Render va lire `render.yaml`.
5. Valide la creation.
6. Render va creer deux services :
   - `chess-elo-coach-api`
   - `chess-elo-coach-web`

Si tu ne vois pas `Blueprint`, fais dans cet ordre :

1. Clique `Web Services`.
2. Choisis le repo `scottynou/chesslearning`.
3. Configure :
   - Name: `chess-elo-coach-api`
   - Root Directory: `backend`
   - Runtime: `Docker`
   - Plan: `Free`
4. Ajoute ces variables :

```env
AI_PROVIDER=heuristic
STOCKFISH_PATH=/usr/games/stockfish
FRONTEND_ORIGIN=https://chess-elo-coach-web.onrender.com
FRONTEND_ORIGIN_REGEX=https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app|https://.*\.onrender\.com
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_PER_WINDOW=45
```

5. Deploie le backend.
6. Verifie :

```text
https://chess-elo-coach-api.onrender.com/health
```

7. Ensuite clique `Static Sites`.
8. Choisis le meme repo.
9. Configure :
   - Name: `chess-elo-coach-web`
   - Root Directory: `frontend`
   - Build Command: `npm install && npm run build:live-server`
   - Publish Directory: `out`
10. Ajoute seulement si Render ne l'a pas cree automatiquement :

```env
NEXT_PUBLIC_API_BASE_URL=https://URL-DE-TON-BACKEND.onrender.com
```

11. Deploie le frontend.
12. Ouvre :

```text
https://chess-elo-coach-web.onrender.com
```

## Apres deploiement

Envoie a Codex :

```text
Backend Render: https://...
Frontend Render: https://...
```

Si Render a modifie les URLs exactes, Codex ajustera `render.yaml` et les variables.

## Limite du gratuit

Le backend gratuit peut dormir apres une periode sans trafic. Le premier appel apres une pause peut etre lent. C'est normal.
