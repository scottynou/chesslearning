# Deploiement Firebase Hosting + Cloud Run

Objectif : remplacer Render par une architecture plus stable.

- Frontend : Firebase Hosting, fichiers statiques `frontend/out`.
- Backend : Google Cloud Run, container Docker `backend/Dockerfile` avec Stockfish.
- API : le frontend appelle le meme domaine Firebase, puis `firebase.json` redirige les routes API vers Cloud Run.

## Pourquoi ce choix

Render free peut dormir et provoquer des cold starts. Cloud Run peut aussi scale a zero, mais on peut fixer `min-instances=1` pour garder une instance chaude. Ce mode coute un peu plus, mais il est beaucoup plus stable pour une app avec Stockfish.

## Ce que j'ai prepare dans le repo

- `firebase.json` : Hosting + rewrites vers Cloud Run `chess-elo-coach-api` en `europe-west1`.
- `frontend/scripts/build-firebase.mjs` : build Next avec `NEXT_PUBLIC_API_BASE_URL=same-origin`, donc appels API en meme origine.
- `scripts/deploy-cloudrun.ps1` : deploie le backend Docker sur Cloud Run.
- `scripts/deploy-firebase-hosting.ps1` : deploie le frontend sur Firebase Hosting.
- `backend/.gcloudignore` : evite d'uploader les fichiers locaux inutiles.
- CORS backend elargi aux domaines `web.app` et `firebaseapp.com`.

## A installer une seule fois

1. Google Cloud CLI :
   https://cloud.google.com/sdk/docs/install

2. Firebase CLI :

```powershell
npm install -g firebase-tools
```

3. Connexion :

```powershell
gcloud auth login
firebase login
```

## Projet Firebase / Google

Dans Firebase Console :

1. Cree ou choisis ton projet.
2. Active Firebase Hosting.
3. Recupere le project id, par exemple `chesslearning-12345`.
4. Copie `.firebaserc.example` vers `.firebaserc`.
5. Remplace `TON_PROJECT_ID_FIREBASE` par ton vrai project id.

## Deployer le backend Cloud Run

Depuis la racine du repo :

```powershell
.\scripts\deploy-cloudrun.ps1 -ProjectId TON_PROJECT_ID_FIREBASE
```

Par defaut :

- service : `chess-elo-coach-api`
- region : `europe-west1`
- min instances : `1`
- max instances : `3`
- memoire : `1Gi`

Si tu veux economiser et accepter les cold starts :

```powershell
.\scripts\deploy-cloudrun.ps1 -ProjectId TON_PROJECT_ID_FIREBASE -MinInstances 0
```

## Deployer le frontend Firebase Hosting

```powershell
.\scripts\deploy-firebase-hosting.ps1 -ProjectId TON_PROJECT_ID_FIREBASE
```

Le script Firebase lance automatiquement :

```powershell
npm --prefix frontend ci
npm --prefix frontend run build:firebase
```

Puis il publie `frontend/out`.

## Verification

Ouvre :

```text
https://TON_PROJECT_ID_FIREBASE.web.app
```

Puis teste :

```text
https://TON_PROJECT_ID_FIREBASE.web.app/health
```

Tu dois recevoir un JSON avec :

```json
{"ok": true, "stockfishConfigured": true}
```

Dans le navigateur, les appels comme `/plan-recommendations` et `/bot-move` doivent partir vers le domaine Firebase, pas directement vers `run.app`.

## Notes importantes

- `min-instances=1` est le reglage stabilite. Il garde une instance chaude, donc facture un minimum.
- `min-instances=0` est le reglage economie. Moins cher, mais cold starts possibles.
- Firebase Hosting a un timeout de 60 secondes sur les rewrites Cloud Run. Ton API doit rester rapide, ce qui est l'objectif des optimisations Stockfish deja ajoutees.
- Si tu changes la region ou le nom du service Cloud Run, modifie aussi `firebase.json`.
