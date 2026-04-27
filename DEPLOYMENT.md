# Deploiement public

Chemin choisi pour ce projet :

- Frontend : Vercel, avec `frontend/` comme dossier racine.
- Backend : Render Web Service Docker, avec `backend/Dockerfile`.
- Moteur : Stockfish installe dans l'image Docker.
- IA : `AI_PROVIDER=heuristic` par defaut, donc aucun cout API.

## 1. Ce que le repo prepare deja

- `frontend/next.config.mjs` exporte un site statique dans `frontend/out`.
- `frontend/vercel.json` indique a Vercel de lancer `npm run build:live-server` et de servir `out`.
- `backend/Dockerfile` installe Stockfish Linux et demarre FastAPI avec `uvicorn`.
- `render.yaml` decrit le service Render gratuit `chess-elo-coach-api`.
- Le backend accepte les domaines `*.vercel.app` via CORS pour eviter un blocage au premier deploiement.
- Les endpoints couteux sont limites par IP avec `RATE_LIMIT_PER_WINDOW=45` sur `60` secondes.

## 2. Ce que tu fais sur GitHub

Pousse le repo sur GitHub, ou laisse Codex le faire si le remote est deja connecte.

Repository actuel attendu :

```text
https://github.com/scottynou/chesslearning.git
```

## 3. Ce que tu fais sur Render

1. Va sur Render.
2. Clique `New` puis `Blueprint`.
3. Connecte GitHub.
4. Choisis le repo `scottynou/chesslearning`.
5. Render lit `render.yaml`.
6. Valide la creation du service.
7. Attends la fin du build Docker.
8. Ouvre l'URL Render terminee par `.onrender.com`.
9. Teste :

```text
https://TON-BACKEND.onrender.com/health
```

La reponse doit ressembler a :

```json
{"ok":true,"stockfishConfigured":true,"aiProvider":"heuristic"}
```

Note cette URL backend.

## 4. Ce que tu fais sur Vercel

1. Va sur Vercel.
2. Importe le repo GitHub `scottynou/chesslearning`.
3. Dans `Root Directory`, choisis `frontend`.
4. Ajoute la variable d'environnement :

```env
NEXT_PUBLIC_API_BASE_URL=https://TON-BACKEND.onrender.com
```

5. Lance le deploiement.
6. Ouvre l'URL Vercel terminee par `.vercel.app`.
7. Teste le parcours :
   - choisir les blancs ;
   - choisir une ouverture ;
   - jouer un coup ;
   - verifier que les recommandations s'affichent.

## 5. Apres ton premier deploiement

Envoie a Codex ces deux URLs :

```text
Backend Render: https://TON-BACKEND.onrender.com
Frontend Vercel: https://TON-FRONTEND.vercel.app
```

Codex pourra ensuite verrouiller `FRONTEND_ORIGIN` sur ton vrai domaine, mettre a jour la doc si besoin, relancer les tests, puis pousser la correction.

## 6. Limite du gratuit

Render gratuit met le backend en veille apres environ 15 minutes sans trafic. Le premier appel apres une pause peut prendre environ une minute. C'est normal pour le mode gratuit.
