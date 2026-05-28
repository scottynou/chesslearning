import type { CoachHumanProfile } from "./eloAdaptation";

export type AccuracySample = {
  ply: number;
  uci: string;
  san?: string;
  accuracy: number;
  centipawnLoss: number;
  quality: "excellent" | "good" | "playable" | "inaccurate" | "mistake" | "blunder";
};

export type AccuracySessionSummary = {
  samples: AccuracySample[];
  count: number;
  averageAccuracy: number;
  weightedAccuracy: number;
  acpl: number;
  counts: Record<AccuracySample["quality"], number>;
  targetBand: AccuracyTargetBand;
};

export type AccuracyTargetBand = {
  profile: CoachHumanProfile;
  target: number;
  min: number;
  max: number;
};

export const ACCURACY_TARGETS: Record<CoachHumanProfile, AccuracyTargetBand> = {
  beginner: { profile: "beginner", target: 72, min: 64, max: 80 },
  lambda: { profile: "lambda", target: 79, min: 72, max: 86 },
  strong: { profile: "strong", target: 84, min: 77, max: 90 },
  veryStrong: { profile: "veryStrong", target: 88, min: 82, max: 93 }
};

const EMPTY_COUNTS: AccuracySessionSummary["counts"] = {
  excellent: 0,
  good: 0,
  playable: 0,
  inaccurate: 0,
  mistake: 0,
  blunder: 0
};

export function targetBandForProfile(profile: CoachHumanProfile): AccuracyTargetBand {
  return ACCURACY_TARGETS[profile];
}

export function summarizeSession(samples: AccuracySample[], profile: CoachHumanProfile): AccuracySessionSummary {
  const counts: AccuracySessionSummary["counts"] = { ...EMPTY_COUNTS };
  let accuracySum = 0;
  let cplSum = 0;
  for (const sample of samples) {
    counts[sample.quality] += 1;
    accuracySum += sample.accuracy;
    cplSum += sample.centipawnLoss;
  }
  const count = samples.length;
  const averageAccuracy = count > 0 ? accuracySum / count : 0;
  const weightedAccuracy = averageAccuracy;
  const acpl = count > 0 ? cplSum / count : 0;
  return {
    samples,
    count,
    averageAccuracy,
    weightedAccuracy,
    acpl,
    counts,
    targetBand: targetBandForProfile(profile)
  };
}

export function bandStatus(accuracy: number, band: AccuracyTargetBand): "under" | "in" | "over" {
  if (accuracy < band.min) return "under";
  if (accuracy > band.max) return "over";
  return "in";
}
