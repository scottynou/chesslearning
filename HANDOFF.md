# Chess Elo Coach — Handoff document

Ce document récapitule l'intégralité du projet pour reprendre le travail à plusieurs.

- **App en live** : https://chess-learner-dd179.web.app
- **Repo GitHub** : https://github.com/scottynou/chesslearning
- **Branche de travail** : `codex/human-elo-profiles`
- **Backend Cloud Run** : `chess-elo-coach-api` (europe-west1, projet `chess-learner-dd179`)

---

## 1. Vision produit

Un coach d'échecs qui :
- Te recommande un coup à chaque tour
- Adapte ses conseils à un **profil humain** (1500 / 2000 / 3000) et un **style** (équilibré, agressif, solide, créatif, pédagogique)
- Ne joue pas comme une machine : il vise une accuracy chess.com cible (~70 / 75 / 85% selon le profil) au lieu de toujours pousser le meilleur coup
- **Mais protège du losing** : si la position devient mauvaise, il débride progressivement et finit par recommander le meilleur coup moteur
- Suit un **plan d'ouverture** sélectionné par l'utilisateur (Italian, London, Sicilian…), adapte la suite si l'adversaire dévie
- L'adversaire (bot) est toujours Stockfish au max

---

## 2. Architecture

### Frontend
- **Stack** : Next.js 16 (App Router), React, TypeScript, `react-chessboard`, `chess.js`
- **Déploiement** : Firebase Hosting (statique, export Next.js)
- **PWA** : manifest + service worker (cache shell, pas le backend)
- **Pas d'auth / pas de DB** : tout en localStorage côté client

### Backend
- **Stack** : FastAPI (Python 3.12), uvicorn
- **Déploiement** : Cloud Run, image Docker multi-stage
- **Moteurs embarqués** :
  - **Stockfish** (paquet Debian, `/usr/games/stockfish`)
  - **lc0** (compilé depuis source dans le Dockerfile, stage 1) + **Maia weights** (maia-1500.pb.gz, maia-1900.pb.gz téléchargés depuis CSSLab/maia-chess)
- **Cache mémoire** : `MemoryCache` (TTL 15–30 min selon route)
- **min-instances=1** : pas de cold start utilisateur

### Communication
- `firebase.json` rewrites les routes API (`/plan-recommendations`, `/review-move`, etc.) vers le service Cloud Run
- Cache navigateur géré par `MemoryCache` côté serveur — les positions communes (ouvertures) sont quasi instantanées

---

## 3. Concepts cœur — comment ça marche

### 3.1 Les trois profils humains
Défini dans `frontend/lib/eloAdaptation.ts` :

| Profil | ELO base | Cible accuracy chess.com |
|--------|----------|-------------------------|
| `lambda` | 1500 | ~70% (max 75%) |
| `strong` | 2000 | ~75% (max 78%) |
| `veryStrong` | 3000 | ~82-85% (max 85%) |

Choisi au démarrage (écran d'accueil → côté → profil → style → plan).

### 3.2 Les styles coach
Défini dans `frontend/lib/eloAdaptation.ts`, appliqué dans `backend/app/strategy/scoring_profile.py:coach_style_modifiers` :

| Style | Effet |
|-------|-------|
| `balanced` | Aucun biais |
| `aggressive` | Tolère plus de risque tactique, moins de simplicité |
| `solid` | Pénalise le risque, prime la simplicité |
| `creative` | Bonus pour les coups de rang 2-5 (sortir du top engine) |
| `educational` | Très haute simplicité (développement, roque, motifs classiques) |

En crise, les modifiers de style sont **atténués** linéairement (cf `style_strength` dans `human_accuracy_sort_score`).

### 3.3 Les bandes d'accuracy
Dans `backend/app/strategy/scoring_profile.py:accuracy_bands_for_profile` — par profil et par "mode" :

- `normal` : jeu standard
- `favorable` : position gagnante
- `pressure` : adversaire fort ou position à risque
- `survival` : critique, on veut le meilleur coup
- `draw_warning` / `draw_critical` : risque de nulle
- `conversion` : finale gagnante à convertir

Chaque bande définit `{target, min, max, planTolerance}`. Le système cherche un coup dont `engineScore` (calculé à partir de `100 - centipawn_loss/8`) tombe dans `[min, max]`, idéalement proche de `target`.

### 3.4 Crisis factor (débridage progressif)
Dans `backend/app/strategy/scoring_profile.py:compute_crisis_factor` :

| Évaluation Stockfish (côté joueur) | Crisis factor |
|--------|---------------|
| ≥ -80 cp | 0.00 (normal) |
| -80 à -150 cp | 0.00 → 0.25 |
| -150 à -260 cp | 0.25 → 0.75 |
| -260 à -400 cp | 0.75 → 1.0 |
| < -400 cp ou mat | 1.0 (survival) |
| Bonus draw warning | +0.12 |
| Bonus draw critical | +0.28 |

Quand crisis > 0, les bandes sont **interpolées** linéairement vers la bande `survival`. Au max (crisis=1), on joue le meilleur coup engine.

### 3.5 Maia humanization
Dans `backend/app/maia_engine.py` :
- Au boot, l'app spawn une instance lc0 par niveau (1500 et 1900)
- Pour chaque position, on appelle `lc0 --weights=maia-XXXX.pb.gz` avec `go nodes 1` → on récupère les probabilités humaines pour chaque coup
- En parallèle de Stockfish (ThreadPoolExecutor partagé dans `plan_engine.py`)
- **Désactivé quand crisis_factor > 0.35** (on veut le meilleur coup, pas le coup humain)
- Mapping :
  - profil `lambda` → maia-1500
  - profil `strong` ou `veryStrong` → maia-1900

Le bonus Maia dans le scoring final : `maia_prob * 40 * style_strength` (max +40 points pour un coup que Maia juge probable).

### 3.6 Scoring final d'un coup
Dans `backend/app/strategy/plan_engine.py:human_accuracy_sort_score` — pour chaque coup candidat :

```
score = in_band_bonus (+26 si dans [min, max])
      + top_engine_bonus (+38 max si rang 1)
      + elite_practical_bonus (pour veryStrong, rangs 2-6)
      + plan_bonus (+10 si suit le plan d'ouverture)
      + creative_rank_bonus (style creative)
      + maia_bonus (jusqu'à +25)
      + final_score * weight
      + plan_fit * weight
      + simplicity * weight (avec bonus du style)
      + engine_score * weight
      + opening_safety_adjustment (bonus roque/centre, pénalité Th3/a4 prématurés)
      + draw_avoidance_bonus
      + elite_crisis_adjustment
      + deterministic_human_variation (-1.2 à +1.2)
      - risk * risk_multiplier (modulé par style)
      - abs(engine_score - target) * distance_penalty
      - max(0, minimum - engine_score) * under_penalty (pénalité gros si en dessous du min)
      - max(0, engine_score - maximum) * over_penalty (pénalité si trop "parfait")
      - anti_perfection_penalty (élite seulement)
```

Le coup avec le score le plus haut devient le `primaryMove` recommandé.

### 3.7 Adaptive ELO boost
Côté frontend (`lib/eloAdaptation.ts`), un boost (+100 à +300) s'applique automatiquement quand :
- Le joueur fait une gaffe (signal du backend)
- L'adversaire joue très fort (signal `opponentStrength`)
- La position devient mauvaise

Le boost augmente l'ELO effectif envoyé au backend, qui durcit les bandes. Décroît avec les coups stables.

---

## 4. Features utilisateur

### Pendant la partie
- **Plateau responsive** : `min(96vw, 100svh - 11rem)`, aspect-ratio 1/1, ResizeObserver pour adapter `react-chessboard`
- **Accuracy meter compact** au-dessus du board : valeur courante, cible (bande verte), curseur, code couleur (vert/orange/rouge)
- **Coup recommandé** : flèche dorée sur le board + carte avec explication pédagogique
- **Coup adverse attendu** : flèche différente, anticipation
- **Contrôles** : `[image-import] [<] [>] [Reset] [Tourner] [Édit]`
- **Édit** : passe le board en mode libre (drag any piece anywhere, click droit = retirer) puis dialog "au trait ?" → applique
- **ELO collapsible** discret en bas (ouvre/ferme)

### Menu hamburger
- **Mes parties** : 50 dernières parties en localStorage, click → réouvre le bilan post-partie
- **Mes erreurs récurrentes** : agrège blunders/mistakes/inaccurate sur les 20 dernières parties par phase (ouverture / mi-jeu / finale) + suggestion
- **Importer un PGN** : colle un PGN chess.com/lichess, l'app rejoue les coups
- **Entraînement tactique** : 18 puzzles curated (mate in 1/2, fork, pin, skewer, etc.), stats persistées
- **Changer de plan** : pendant la partie, switch d'ouverture sans perdre la position
- **Langue FR/EN** : switch live (sauf coach narratives qui restent en français)

### Post-partie
- Modal automatique avec :
  - Accuracy globale (moyenne simple des coups revus)
  - ACPL (average centipawn loss)
  - Compteurs par qualité (excellent / bon / jouable / imprécis / erreur / gaffe)
  - Top 3 des pires coups
- Sauvegardé auto en localStorage

---

## 5. Carte des fichiers — où trouver quoi

### Backend (`backend/app/`)

| Fichier | Rôle |
|---------|------|
| `main.py` | FastAPI entrypoint, routes (`/plan-recommendations`, `/review-move`, `/bot-move`, `/health`, `/debug/maia-*`), caches, warmup au boot |
| `schemas.py` | Modèles Pydantic (request/response), enums `HumanProfile`, `CoachStyle`, etc. |
| `stockfish_engine.py` | Client UCI Stockfish persistent (thread-safe, cache 120s) |
| `maia_engine.py` | Client UCI lc0+Maia (singleton par niveau, output parser robuste v0.30/v0.31) |
| `elo_ranker.py` | Calcul des scores par coup (engine/human/simplicity/risk) |
| `review_service.py` | Analyse post-coup (quality, accuracy %, cp loss) |
| `accuracy_math.py` | Formules pures Lichess (cp → win%, accuracy %) — sans deps lourdes pour les tests |
| `evaluation_label.py` | Centipawns → libellé français |
| `beginner_notation.py` | UCI/SAN → libellé débutant (♘ Cavalier b1 → c3) |
| `pv_translator.py` | Variations Stockfish → explications simples |
| `cache.py` | MemoryCache TTL |
| `explanation_service.py` | Orchestrateur explications (heuristique ou Gemini) |
| `ai_reranker.py` | Réordonne les candidats via LLM (optionnel) |
| `image_import_service.py` | OCR de position via Gemini Vision |
| `live_plan_insight_service.py` | Insights temps réel |
| `ai_providers/` | heuristic / openai / gemini / ollama |
| `strategy/plan_engine.py` | **Le gros morceau (~2300 lignes)**. Orchestrateur principal de `/plan-recommendations` : phase detection, accuracy profile, crisis, Maia query, scoring, ranking, fallbacks |
| `strategy/scoring_profile.py` | Bandes d'accuracy, crisis factor, style modifiers (extrait, testable sans deps) |
| `strategy/opening_coach.py` | Chargement des plans, détection ouverture, transposition par FEN, déviations adverses |
| `strategy/middlegame_coach.py` / `endgame_coach.py` | Signaux analytiques uniquement (pieces en prise, colonnes ouvertes, comptage matériel). Pas de cours écrit. |
| `strategy/move_merger.py` | Fusionne moves du plan et moves engine |
| `strategy/phase_detector.py` | Opening / transition / middlegame / endgame |
| `data/opening_plans/` | JSON des plans d'ouverture (white, black vs e4/d4/flexible, situational, hidden) |

### Frontend (`frontend/`)

| Fichier | Rôle |
|---------|------|
| `app/page.tsx` | **Composant principal (~2800 lignes)**. State, navigation snapshot, useEffects pour `/plan-recommendations` + bot move + accuracy, mode édition, tous les modals |
| `app/layout.tsx` | RootLayout Next, métadata PWA, registration service worker |
| `app/globals.css` | **TOUS les styles** dans un fichier unique |
| `components/ChessCoachBoard.tsx` | Wrapper `react-chessboard` avec ResizeObserver, modes locked/thinking/editMode, highlights, flèches |
| `components/AccuracyMeter.tsx` | Affichage compact accuracy actuelle vs bande cible |
| `components/PostGameReview.tsx` | Modal bilan post-partie |
| `components/SavedGamesPanel.tsx` | Liste des parties sauvegardées + réouverture bilan |
| `components/MistakePatternsPanel.tsx` | Agrégation erreurs récurrentes |
| `components/TacticalTrainingPanel.tsx` | UI des puzzles tactiques |
| `components/PgnImportModal.tsx` | Import PGN |
| `components/PlanSwitchModal.tsx` | Switch de plan en cours de partie |
| `components/SideSelectionPanel.tsx` | Écran d'accueil 3 étapes (côté → profil → style) |
| `components/PositionEditorModal.tsx` | **Déprécié** — l'édition se fait maintenant inline via le bouton Édit |
| `components/GameControls.tsx`, `MoveHistory.tsx`, `OpeningRepertoirePanel.tsx`, `PlanFirstPanel.tsx`, `LastMoveReviewPanel.tsx` | UI existante (panels d'historique, sélection de plans, etc.) |
| `lib/api.ts` | Client HTTP vers le backend (fetch JSON, abort signals) |
| `lib/types.ts` | Types TypeScript miroirs des schemas Pydantic |
| `lib/eloAdaptation.ts` | Profils, styles, calcul ELO effectif, boost adaptatif |
| `lib/accuracySession.ts` | Agrégation accuracy session (samples, moyenne simple, ACPL) |
| `lib/useAccuracySession.ts` | Hook React qui appelle `/review-move` après chaque coup joueur |
| `lib/gameHistory.ts` | localStorage `chess_learner_games_v1` (max 50) |
| `lib/mistakeTracker.ts` | Analyse des patterns d'erreurs |
| `lib/puzzles.ts` | Dataset des puzzles tactiques |
| `lib/i18n.ts` | Dictionnaires FR/EN + hook `useI18n` |
| `lib/editableBoard.ts` | Helpers FEN ↔ EditableBoard (utilisé par image import) |
| `lib/chess.ts`, `lib/moveTimeline.ts`, `lib/openingVisuals.ts`, `lib/evaluationLabel.ts`, `lib/beginnerNotation.ts` | Utilitaires divers |
| `public/manifest.webmanifest` | Manifest PWA |
| `public/sw.js` | Service worker (cache shell, bypass API) |

### Tests
- `backend/tests/test_accuracy_and_crisis.py` — bandes, crisis factor, styles (13 cas)
- `backend/tests/test_plan_first.py` — accuracy profiles dans le contexte du plan engine
- `backend/tests/test_elo_ranker.py` / `test_v2_coach.py` / `test_schemas.py` / `test_stockfish_engine.py` / `test_image_import_service.py` / `test_ai_provider_selection.py`
- **109 tests passants** au total — `python -m pytest tests/`

---

## 6. Déploiement

### Frontend (Firebase Hosting)
```bash
cd chess-elo-coach
firebase deploy --only hosting
```
- Build Next.js statique → `frontend/out/`
- Upload Firebase Hosting
- Routes API rewrites vers Cloud Run via `firebase.json`

### Backend (Cloud Run)
```bash
cd chess-elo-coach
gcloud run deploy chess-elo-coach-api \
  --source ./backend \
  --region europe-west1 \
  --allow-unauthenticated \
  --min-instances 1 \
  --max-instances 2 \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 10 \
  --timeout 600 \
  --update-env-vars 'AI_PROVIDER=auto,...,MAIA_ENABLED=true,LC0_PATH=/opt/lc0/lc0,MAIA_WEIGHTS_DIR=/opt/maia-weights'
```
- Build Docker (~8-10 min : compile lc0 from source + download Maia weights ~300MB)
- Vérifier ensuite : `curl https://chess-elo-coach-api-862065898111.europe-west1.run.app/health`

### Variables d'env Cloud Run importantes
- `AI_PROVIDER=auto` (heuristic / openai / gemini / ollama)
- `GEMINI_API_KEY=...` (pour les narratives + image import)
- `STOCKFISH_PATH=/usr/games/stockfish`
- `MAIA_ENABLED=true`
- `LC0_PATH=/opt/lc0/lc0`
- `MAIA_WEIGHTS_DIR=/opt/maia-weights`
- `STOCKFISH_RECOMMEND_MS=700` (movetime par défaut)
- `STOCKFISH_CRITICAL_MS=1200` (en survival)
- `RATE_LIMIT_PER_WINDOW=45` (par IP / 60s)

---

## 7. État connu / limitations / TODO

### Tuning à vérifier
- **Maia bias réduit** : `maia_bonus` est maintenant à 25 et le seuil de désactivation Maia est `crisis_factor > 0.20`. Le prochain réglage utile est une vraie calibration par positions ou self-play.
- Les targets d'accuracy (70/75/85) sont des constantes dans `scoring_profile.accuracy_bands_for_profile` — facile à ajuster.

### Limitations actuelles
- **Pas d'auth ni de DB serveur** : tout est local au navigateur. Si l'utilisateur change d'appareil, perd ses parties.
- **i18n partielle** : seuls le menu hamburger, l'accuracy meter, le post-game review, et quelques modals sont traduits. Les narratives coach (backend) restent en français.
- **Pas de WASM Stockfish** : l'app ne fonctionne pas offline (le backend est sollicité à chaque coup).
- **Pas de multijoueur** ni de commentateur IA (explicitement non demandés).
- **`plan_engine.py` fait 2300+ lignes** : la fonction `human_accuracy_sort_score` mériterait d'être extraite, idem pour l'opening_safety_adjustment.

### Endpoints debug en prod
- `GET /health` : statut Stockfish + Maia (booleans pour binaire/poids présents)
- `GET /debug/maia-test` : exécute lc0 brut pour diagnostiquer
- `GET /debug/maia-suggest` : appelle `MaiaEngine.suggest_with_raw` pour voir le format brut lc0

À garder ou supprimer plus tard.

### Branches Git
- `main` : ancienne version stable (avant cette série de modifs)
- `codex/human-elo-profiles` : **branche active**, tout le travail récent

Une fusion vers `main` (via PR) serait propre à un moment donné.

---

## 8. Premiers pas pour le collaborateur

1. **Cloner** : `git clone https://github.com/scottynou/chesslearning.git`
2. **Checkout** : `git checkout codex/human-elo-profiles`
3. **Backend local** :
   ```bash
   cd backend
   python -m venv .venv
   .venv/Scripts/activate  # ou source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
4. **Frontend local** :
   ```bash
   cd frontend
   npm install
   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
   ```
5. **Tests** : `cd backend && python -m pytest tests/`
6. **TypeScript check** : `cd frontend && npx tsc --noEmit`

### Pour comprendre un endpoint
- Backend : commencer par `main.py` → trouver la route → lire la fonction → tracer vers `plan_engine.py` ou autre service
- Frontend : commencer par `app/page.tsx` → trouver le useEffect ou handler qui appelle l'API → tracer vers `lib/api.ts`

### Pour ajouter une feature
1. Si elle touche au scoring : modifier `scoring_profile.py` (extrait, testable)
2. Si elle touche au flow utilisateur : créer un nouveau composant React + le wirer dans `page.tsx`
3. Si elle touche au schéma de communication : modifier `schemas.py` (backend) + `types.ts` (frontend) en miroir
4. Ajouter un test dans `tests/` pour les changements de logique

---

## 9. Conventions

- **Pas de fichiers > 3000 lignes** créés intentionnellement. Si on doit y revenir, refactorer.
- **Pas d'emoji dans le code** sauf si explicitement demandé.
- **Commits descriptifs** avec corps multi-lignes pour les changements non triviaux.
- **Tests passants** avant push (98/98 actuellement).
- **TypeScript strict** : `npx tsc --noEmit` doit passer cleanly.
- **Pas de console.log laissés** dans le code committé (seulement `logger.info/warning` côté backend).
