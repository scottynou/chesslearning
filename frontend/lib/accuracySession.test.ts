import { describe, expect, it } from "vitest";

import { ACCURACY_TARGETS, summarizeSession, type AccuracySample } from "./accuracySession";

const samples: AccuracySample[] = [
  { ply: 1, uci: "e2e4", accuracy: 100, centipawnLoss: 0, quality: "excellent" },
  { ply: 3, uci: "g1f3", accuracy: 80, centipawnLoss: 45, quality: "good" },
  { ply: 5, uci: "f1c4", accuracy: 60, centipawnLoss: 120, quality: "inaccurate" }
];

describe("accuracySession", () => {
  it("uses Chess.com-style average game accuracy instead of harmonic scoring", () => {
    const summary = summarizeSession(samples, "lambda");

    expect(summary.averageAccuracy).toBeCloseTo(80, 5);
    expect(summary.weightedAccuracy).toBeCloseTo(80, 5);
    expect(summary.acpl).toBeCloseTo(55, 5);
  });

  it("keeps profile target bands aligned with calibrated Elo buckets", () => {
    expect(ACCURACY_TARGETS.beginner).toMatchObject({ target: 72, min: 64, max: 80 });
    expect(ACCURACY_TARGETS.lambda).toMatchObject({ target: 79, min: 72, max: 86 });
    expect(ACCURACY_TARGETS.strong).toMatchObject({ target: 84, min: 77, max: 90 });
    expect(ACCURACY_TARGETS.veryStrong).toMatchObject({ target: 88, min: 82, max: 93 });
  });
});
