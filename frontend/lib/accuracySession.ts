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
  lambda: { profile: "lambda", target: 70, min: 65, max: 75 },
  strong: { profile: "strong", target: 75, min: 70, max: 78 },
  veryStrong: { profile: "veryStrong", target: 82, min: 78, max: 85 }
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
  const weightedAccuracy = harmonicMeanAccuracy(samples);
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

// Lichess uses a weighted/harmonic combination so a single blunder is not lost
// in the average of a long forced game. We approximate with harmonic mean which
// is more sensitive to low values.
function harmonicMeanAccuracy(samples: AccuracySample[]): number {
  if (samples.length === 0) return 0;
  let denom = 0;
  for (const sample of samples) {
    const value = Math.max(1, sample.accuracy);
    denom += 1 / value;
  }
  return samples.length / denom;
}

export function bandStatus(accuracy: number, band: AccuracyTargetBand): "under" | "in" | "over" {
  if (accuracy < band.min) return "under";
  if (accuracy > band.max) return "over";
  return "in";
}
