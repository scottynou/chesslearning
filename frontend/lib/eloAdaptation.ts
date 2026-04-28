import type { SkillLevel } from "./types";

export const ELO_MIN = 600;
export const ELO_MAX = 3200;
export const ELO_STEP = 50;
export const DEFAULT_BASE_ELO = 1200;
export const MAX_ADAPTIVE_BOOST = 400;

export type EloQuality = "excellent" | "good" | "playable" | "inaccurate" | "mistake" | "blunder";

export type EloAdaptationContext = {
  currentBoost: number;
  autoEnabled: boolean;
  playerReviewQuality?: EloQuality | null;
  phaseStatus?: string | null;
  primaryWarning?: string | null;
  primaryEngineScore?: number | null;
  primaryTacticalRisk?: number | null;
  stablePlyCount?: number;
  currentPly?: number | null;
  lastAdjustedPly?: number | null;
};

export function clampElo(value: number) {
  return clamp(Math.round(value), ELO_MIN, ELO_MAX);
}

export function normalizeBaseElo(value: number) {
  const stepped = Math.round(value / ELO_STEP) * ELO_STEP;
  return clampElo(stepped);
}

export function normalizeAdaptiveBoost(value: number) {
  const stepped = Math.round(value / ELO_STEP) * ELO_STEP;
  return clamp(stepped, 0, MAX_ADAPTIVE_BOOST);
}

export function effectiveElo(baseElo: number, adaptiveBoost: number) {
  return clampElo(normalizeBaseElo(baseElo) + normalizeAdaptiveBoost(adaptiveBoost));
}

export function skillLevelForElo(elo: number): SkillLevel {
  const normalized = clampElo(elo);
  if (normalized <= 1400) return "beginner";
  if (normalized <= 2350) return "intermediate";
  return "pro";
}

export function nextStablePlyCount({
  currentStablePlyCount,
  quality,
  hasDanger
}: {
  currentStablePlyCount: number;
  quality?: EloQuality | null;
  hasDanger?: boolean;
}) {
  if (hasDanger || !quality || quality === "inaccurate" || quality === "mistake" || quality === "blunder") {
    return 0;
  }
  return currentStablePlyCount + 1;
}

export function nextAdaptiveBoost(context: EloAdaptationContext) {
  const currentBoost = normalizeAdaptiveBoost(context.currentBoost);
  if (!context.autoEnabled) return 0;
  if (context.currentPly != null && context.lastAdjustedPly === context.currentPly) return currentBoost;

  const hasStrongDanger = Boolean(context.primaryWarning) || (context.primaryTacticalRisk ?? 0) >= 45;
  const weakPrimary = (context.primaryEngineScore ?? 100) <= 45 || (context.primaryTacticalRisk ?? 0) >= 32;
  const stronglyAdapted = context.phaseStatus === "adapted" || context.phaseStatus === "fallback";

  let targetBoost = currentBoost;
  if (context.playerReviewQuality === "mistake" || context.playerReviewQuality === "blunder" || hasStrongDanger) {
    targetBoost += 200;
  } else if (context.playerReviewQuality === "inaccurate" || stronglyAdapted || weakPrimary) {
    targetBoost += 100;
  } else if ((context.stablePlyCount ?? 0) >= 2) {
    targetBoost -= 50;
  }

  targetBoost = normalizeAdaptiveBoost(targetBoost);
  const rawDelta = targetBoost - currentBoost;
  const cappedDelta = rawDelta > 0 ? Math.min(100, rawDelta) : Math.max(-50, rawDelta);
  return normalizeAdaptiveBoost(currentBoost + cappedDelta);
}

export function formatEloLabel({
  baseElo,
  adaptiveBoost,
  autoEnabled
}: {
  baseElo: number;
  adaptiveBoost: number;
  autoEnabled: boolean;
}) {
  const base = normalizeBaseElo(baseElo);
  const boost = normalizeAdaptiveBoost(autoEnabled ? adaptiveBoost : 0);
  const effective = effectiveElo(base, boost);
  const boostLabel = autoEnabled ? `Auto +${boost}` : "Auto off";
  return `Niveau ${base} - ${boostLabel} - Effectif ${effective}`;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}
