# Visual Patch — Chess Learning

Cette version remanie fortement la couche visuelle et éditoriale du produit sans modifier volontairement la logique métier, les appels API, le backend, les règles d'échecs ni les flux principaux.

## Direction artistique

- Nouvelle esthétique de laboratoire tactique premium : fonds texturés, grilles d'échiquier, panneaux profonds, halos, contrastes nuit / or / sauge et compositions plus cinématographiques.
- Refonte du design system global dans `frontend/app/globals.css` : variables, boutons, panneaux, cartes, alertes, menu, plateau, coach live, historique, analyse et responsive.
- Plateau renforcé visuellement : cadre sombre premium, flèches dorées, sélection plus lisible, cases harmonisées et meilleure séparation entre zone de jeu et panneaux pédagogiques.

## Écrans remaniés

- Accueil : hero immersif, choix Blancs / Noirs beaucoup plus impactant, mode libre conservé.
- Premier coup blanc pour le flux noir : écran simplifié avec une logique en 3 étapes et moins de texte répétitif.
- Sélection des plans : cartes éditoriales, hiérarchie titre → réponse, détails uniquement au clic.
- Introduction du plan : conservation des explications longues utiles, mais mieux séparées en blocs narratifs, objectifs, missions, chemin, pièges et suite de partie.
- Coach live : nouveau cockpit visuel avec statut, progression, objectif, coup recommandé, alternatives et détails avancés repliables.
- Analyse du dernier coup : résumé compact immédiat, score card, risque principal et analyse complète dans un bloc dépliable.
- Historique, contrôles et menu : harmonisés avec la nouvelle direction visuelle.

## Densité de texte

- Suppression d'une grande partie des répétitions visibles dans les cartes et panneaux courts.
- Regroupement des informations en blocs lisibles : titre, réponse, puis détail si nécessaire.
- Les textes longs restent présents là où ils servent vraiment l'apprentissage : introduction du plan et détails avancés.
- Les informations techniques restent disponibles, mais elles sont moins envahissantes.

## Fonctionnement conservé

- Aucun changement volontaire sur le backend, les services API, le moteur, les règles de déplacement, l'historique, les recommandations de plan, l'analyse de coup, la navigation par URL, le mode bot ou le mode libre.
- Le patch cible principalement le rendu React, les classes de structure et le CSS global.

## Fichiers modifiés principalement

- `frontend/app/globals.css`
- `frontend/app/page.tsx`
- `frontend/components/SideSelectionPanel.tsx`
- `frontend/components/OpeningRepertoirePanel.tsx`
- `frontend/components/PlanFirstPanel.tsx`
- `frontend/components/ChessCoachBoard.tsx`
- `frontend/components/LastMoveReviewPanel.tsx`
- `frontend/components/MoveHistory.tsx`
- `frontend/components/GameControls.tsx`
- `frontend/components/OpeningMiniBoard.tsx`
- `frontend/tailwind.config.ts`

## Vérification locale

- `git diff --check` : OK.
- Parsing TypeScript / TSX via l'API TypeScript : OK, aucune erreur de syntaxe détectée.
- Parsing CSS via PostCSS : OK.
- `npm test` et la compilation TypeScript complète n'ont pas pu être exécutés dans cet environnement car les dépendances locales du frontend ne sont pas installées (`node_modules` absent, donc `vitest`, `next`, `react`, etc. introuvables). Après extraction, lancer `npm install` dans `frontend/`, puis `npm test` et `npm run build`.

## Note de livraison

L'archive est une livraison source propre. Les dépendances générées ou locales (`node_modules`, `.next`, caches, environnements virtuels) ne sont pas incluses. Elles doivent être régénérées dans l'environnement de développement ou de déploiement.
