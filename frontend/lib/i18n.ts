"use client";

import { useCallback, useEffect, useState } from "react";

export type Locale = "fr" | "en";

const STORAGE_KEY = "chess_learner_locale_v1";

type Dict = Record<string, string>;

const FR: Dict = {
  // Menu hamburger
  "menu.myGames": "Mes parties",
  "menu.recurringMistakes": "Mes erreurs récurrentes",
  "menu.importFen": "Importer un FEN",
  "menu.importPgn": "Importer un PGN",
  "menu.tacticalTraining": "Entraînement tactique",
  "menu.calibration": "Equilibre winrate",
  "menu.changePlan": "Changer de plan",
  "menu.editPosition": "Éditer la position",
  "menu.commands": "Commandes et réglages",
  "menu.history": "Historique",
  "menu.accuracy": "Accuracy",
  "menu.techDetails": "Détails techniques",
  "menu.language": "Langue",
  // Side selection
  "side.choose": "Choisis ton camp",
  "side.white": "Blancs",
  "side.black": "Noirs",
  "side.iPlayWhite": "Je joue les blancs",
  "side.iPlayBlack": "Je joue les noirs",
  "side.freeMode": "Mode libre",
  "side.humanStyle": "Style humain",
  "side.coachStyle": "Style du coach",
  "side.back": "Retour",
  // Accuracy meter
  "accuracy.target": "cible",
  "accuracy.lastMove": "Dernier coup",
  // Post-game review
  "review.title": "Bilan de partie",
  "review.globalAccuracy": "Accuracy globale",
  "review.avgAccuracy": "Accuracy moyenne",
  "review.acpl": "ACPL",
  "review.movesAnalyzed": "Coups analysés",
  "review.movesToReview": "Coups à revoir",
  "review.close": "Fermer",
  "review.targetHelp": "cible {min}-{max}% (profil {profile})",
  "review.avgPerMove": "moyenne simple par coup",
  "review.cpLossAvg": "perte de centipions moyenne",
  // Quality
  "quality.excellent": "Excellent",
  "quality.good": "Bon",
  "quality.playable": "Jouable",
  "quality.inaccurate": "Imprécis",
  "quality.mistake": "Erreur",
  "quality.blunder": "Gaffe",
  // Tactical
  "tactical.title": "Entraînement tactique",
  "tactical.difficulty": "Difficulté",
  "tactical.solved": "résolus",
  "tactical.successRate": "% de réussite",
  "tactical.yourTurn": "À toi de jouer",
  "tactical.findBest": "Trouve le coup gagnant",
  "tactical.hint": "Indice",
  "tactical.next": "Puzzle suivant",
  "tactical.skip": "Passer",
  "tactical.wellDone": "Bien joué !",
  "tactical.wrongMove": "Pas le bon coup.",
  "tactical.solutionWas": "La solution était",
  // Plan switch
  "plan.changeTitle": "Changer de plan",
  "plan.changeNote": "Garde la position actuelle. Le coach recalcule les conseils avec le nouveau plan.",
  "plan.noPlan": "Aucun plan (jouer par principes)",
  "plan.tierRecommended": "Recommandé",
  "plan.tierGood": "Bon",
  "plan.tierSituational": "Situationnel",
  "plan.tierHidden": "Avancé",
  // Saved games
  "saved.title": "Mes parties",
  "saved.empty": "Aucune partie sauvegardée pour l'instant.",
  "saved.delete": "Supprimer",
  "saved.back": "← Retour à la liste"
};

const EN: Dict = {
  // Hamburger menu
  "menu.myGames": "My games",
  "menu.recurringMistakes": "Recurring mistakes",
  "menu.importFen": "Import FEN",
  "menu.importPgn": "Import PGN",
  "menu.tacticalTraining": "Tactical training",
  "menu.calibration": "Winrate balance",
  "menu.changePlan": "Change plan",
  "menu.editPosition": "Edit position",
  "menu.commands": "Controls and settings",
  "menu.history": "History",
  "menu.accuracy": "Accuracy",
  "menu.techDetails": "Technical details",
  "menu.language": "Language",
  // Side selection
  "side.choose": "Pick your side",
  "side.white": "White",
  "side.black": "Black",
  "side.iPlayWhite": "I play White",
  "side.iPlayBlack": "I play Black",
  "side.freeMode": "Free mode",
  "side.humanStyle": "Human level",
  "side.coachStyle": "Coach style",
  "side.back": "Back",
  // Accuracy meter
  "accuracy.target": "target",
  "accuracy.lastMove": "Last move",
  // Post-game review
  "review.title": "Game review",
  "review.globalAccuracy": "Overall accuracy",
  "review.avgAccuracy": "Average accuracy",
  "review.acpl": "ACPL",
  "review.movesAnalyzed": "Moves analyzed",
  "review.movesToReview": "Moves to review",
  "review.close": "Close",
  "review.targetHelp": "target {min}-{max}% (profile {profile})",
  "review.avgPerMove": "simple average per move",
  "review.cpLossAvg": "average centipawn loss",
  // Quality
  "quality.excellent": "Excellent",
  "quality.good": "Good",
  "quality.playable": "Playable",
  "quality.inaccurate": "Inaccuracy",
  "quality.mistake": "Mistake",
  "quality.blunder": "Blunder",
  // Tactical
  "tactical.title": "Tactical training",
  "tactical.difficulty": "Difficulty",
  "tactical.solved": "solved",
  "tactical.successRate": "% success rate",
  "tactical.yourTurn": "Your move",
  "tactical.findBest": "Find the winning move",
  "tactical.hint": "Hint",
  "tactical.next": "Next puzzle",
  "tactical.skip": "Skip",
  "tactical.wellDone": "Well played!",
  "tactical.wrongMove": "Not the right move.",
  "tactical.solutionWas": "The solution was",
  // Plan switch
  "plan.changeTitle": "Change plan",
  "plan.changeNote": "Keep the current position. The coach will recompute recommendations with the new plan.",
  "plan.noPlan": "No plan (play by principles)",
  "plan.tierRecommended": "Recommended",
  "plan.tierGood": "Good",
  "plan.tierSituational": "Situational",
  "plan.tierHidden": "Advanced",
  // Saved games
  "saved.title": "My games",
  "saved.empty": "No saved games yet.",
  "saved.delete": "Delete",
  "saved.back": "← Back to list"
};

const DICTS: Record<Locale, Dict> = { fr: FR, en: EN };

function loadLocale(): Locale {
  if (typeof window === "undefined") return "fr";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "fr" || stored === "en") return stored;
    return "fr";
  } catch {
    return "fr";
  }
}

function saveLocale(locale: Locale) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // ignore
  }
}

const localeListeners = new Set<(locale: Locale) => void>();
let currentLocale: Locale = "fr";
let hydrated = false;

export function useI18n() {
  const [locale, setLocaleState] = useState<Locale>(currentLocale);

  useEffect(() => {
    if (!hydrated) {
      currentLocale = loadLocale();
      hydrated = true;
      setLocaleState(currentLocale);
    }
    const listener = (next: Locale) => setLocaleState(next);
    localeListeners.add(listener);
    return () => {
      localeListeners.delete(listener);
    };
  }, []);

  const setLocale = useCallback((next: Locale) => {
    currentLocale = next;
    saveLocale(next);
    localeListeners.forEach((cb) => cb(next));
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const dict = DICTS[locale];
      let value = dict[key] ?? DICTS.fr[key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          value = value.replace(`{${k}}`, String(v));
        }
      }
      return value;
    },
    [locale]
  );

  return { locale, setLocale, t };
}
