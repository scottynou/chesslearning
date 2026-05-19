import type { AccuracySample, AccuracySessionSummary } from "./accuracySession";
import type { CoachHumanProfile, CoachStyle } from "./eloAdaptation";

const STORAGE_KEY = "chess_learner_games_v1";
const MAX_GAMES = 50;

export type SavedGame = {
  id: string;
  savedAt: number;
  result: string;
  pgn: string;
  finalFen: string;
  userSide: "white" | "black" | "both";
  humanProfile: CoachHumanProfile;
  coachStyle: CoachStyle;
  selectedPlanId: string | null;
  selectedPlanName: string | null;
  summary: AccuracySessionSummary;
};

export type SaveGameInput = {
  result: string;
  pgn: string;
  finalFen: string;
  userSide: "white" | "black" | "both";
  humanProfile: CoachHumanProfile;
  coachStyle: CoachStyle;
  selectedPlanId: string | null;
  selectedPlanName: string | null;
  summary: AccuracySessionSummary;
};

export function loadGames(): SavedGame[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((entry): entry is SavedGame => isValidSavedGame(entry));
  } catch {
    return [];
  }
}

export function saveGame(input: SaveGameInput): SavedGame {
  if (typeof window === "undefined") {
    return makeSaved(input);
  }
  const entry = makeSaved(input);
  const existing = loadGames();
  const next = [entry, ...existing].slice(0, MAX_GAMES);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Best-effort. If storage is full or blocked, we drop the persistence.
  }
  return entry;
}

export function deleteGame(id: string): SavedGame[] {
  if (typeof window === "undefined") return [];
  const next = loadGames().filter((entry) => entry.id !== id);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // ignore
  }
  return next;
}

export function clearGames(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

function makeSaved(input: SaveGameInput): SavedGame {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    savedAt: Date.now(),
    ...input
  };
}

function isValidSavedGame(value: unknown): value is SavedGame {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.id === "string" &&
    typeof obj.savedAt === "number" &&
    typeof obj.result === "string" &&
    typeof obj.pgn === "string" &&
    typeof obj.finalFen === "string" &&
    typeof obj.userSide === "string" &&
    typeof obj.humanProfile === "string" &&
    typeof obj.summary === "object" &&
    Array.isArray((obj.summary as { samples?: AccuracySample[] }).samples)
  );
}
