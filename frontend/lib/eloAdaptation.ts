import type { SkillLevel } from "./types";

export const ELO_MIN = 600;
export const ELO_MAX = 3200;
export const ELO_STEP = 50;
export const DEFAULT_BASE_ELO = 1200;
export const MAX_ADAPTIVE_BOOST = 1000;
export const MIN_ADAPTIVE_BOOST = 0;

export type EloQuality = "excellent" | "good" | "playable" | "inaccurate" | "mistake" | "blunder";
export type AdaptivePressure = "stable" | "worse" | "critical" | "drawish";

export type EloTrendState = {
  lastPressure: AdaptivePressure | null;
  pressureStreak: number;
  stableStreak: number;
};

export type AdaptiveSignalApplication = {
  currentBoost: number;
  pressure: AdaptivePressure;
  suggestedBoostDelta: number;
  trend: EloTrendState;
};

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
  return clamp(stepped, MIN_ADAPTIVE_BOOST, MAX_ADAPTIVE_BOOST);
}

export function freshEloTrendState(): EloTrendState {
  return {
    lastPressure: null,
    pressureStreak: 0,
    stableStreak: 0
  };
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
  const cappedDelta = rawDelta > 0 ? Math.min(200, rawDelta) : Math.max(-100, rawDelta);
  return normalizeAdaptiveBoost(currentBoost + cappedDelta);
}

export function applyAdaptiveSignal({
  currentBoost,
  pressure,
  suggestedBoostDelta,
  trend
}: AdaptiveSignalApplication) {
  const current = normalizeAdaptiveBoost(currentBoost);
  const baseDelta = normalizeAdaptiveDelta(suggestedBoostDelta);
  const cleanTrend = normalizeTrendState(trend);

  if (baseDelta > 0) {
    const samePressure = pressure !== "stable" && cleanTrend.lastPressure === pressure;
    const pressureStreak = samePressure ? cleanTrend.pressureStreak + 1 : 1;
    const nextTrend = {
      lastPressure: pressure,
      pressureStreak,
      stableStreak: 0
    };
    const boostedDelta = pressureStreak >= 2 ? baseDelta + pressureStreakBonus(pressure) : baseDelta;
    const nextDelta = Math.min(maxPositiveDeltaForPressure(pressure), boostedDelta);
    const nextBoost = normalizeAdaptiveBoost(current + nextDelta);

    return {
      boost: nextBoost,
      appliedDelta: nextBoost - current,
      trend: nextTrend
    };
  }

  if (baseDelta < 0) {
    const stableStreak = pressure === "stable" ? cleanTrend.stableStreak + 1 : 1;
    const nextTrend = {
      lastPressure: "stable" as const,
      pressureStreak: 0,
      stableStreak
    };
    const calmerDelta = stableStreak >= 4 ? baseDelta - 50 : stableStreak >= 2 ? baseDelta : 0;
    const nextDelta = Math.max(-100, calmerDelta);
    const nextBoost = normalizeAdaptiveBoost(current + nextDelta);

    return {
      boost: nextBoost,
      appliedDelta: nextBoost - current,
      trend: nextTrend
    };
  }

  const stableStreak = pressure === "stable" ? cleanTrend.stableStreak + 1 : 0;
  return {
    boost: current,
    appliedDelta: 0,
    trend: {
      lastPressure: pressure,
      pressureStreak: pressure === "stable" ? 0 : cleanTrend.pressureStreak,
      stableStreak
    }
  };
}

function normalizeAdaptiveDelta(value: number) {
  const stepped = Math.round(value / ELO_STEP) * ELO_STEP;
  return clamp(stepped, -100, 300);
}

function normalizeTrendState(trend: EloTrendState | null | undefined): EloTrendState {
  if (!trend) return freshEloTrendState();
  return {
    lastPressure: trend.lastPressure,
    pressureStreak: Math.max(0, trend.pressureStreak),
    stableStreak: Math.max(0, trend.stableStreak)
  };
}

function pressureStreakBonus(pressure: AdaptivePressure) {
  if (pressure === "critical") return 100;
  if (pressure === "drawish") return 100;
  if (pressure === "worse") return 75;
  return 0;
}

function maxPositiveDeltaForPressure(pressure: AdaptivePressure) {
  if (pressure === "critical") return 300;
  if (pressure === "drawish") return 250;
  if (pressure === "worse") return 200;
  return 0;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}
