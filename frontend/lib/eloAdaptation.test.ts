import { describe, expect, it } from "vitest";
import {
  effectiveElo,
  formatEloLabel,
  nextAdaptiveBoost,
  nextStablePlyCount,
  normalizeBaseElo,
  skillLevelForElo
} from "./eloAdaptation";

describe("eloAdaptation", () => {
  it("clamps and steps base Elo values", () => {
    expect(normalizeBaseElo(421)).toBe(600);
    expect(normalizeBaseElo(1237)).toBe(1250);
    expect(normalizeBaseElo(3900)).toBe(3200);
    expect(effectiveElo(3150, 400)).toBe(3200);
  });

  it("maps Elo to the internal skill level", () => {
    expect(skillLevelForElo(600)).toBe("beginner");
    expect(skillLevelForElo(1400)).toBe("beginner");
    expect(skillLevelForElo(1450)).toBe("intermediate");
    expect(skillLevelForElo(2350)).toBe("intermediate");
    expect(skillLevelForElo(2400)).toBe("pro");
  });

  it("raises the adaptive boost after a serious mistake without jumping more than 100 Elo", () => {
    expect(nextAdaptiveBoost({ currentBoost: 0, autoEnabled: true, playerReviewQuality: "blunder", stablePlyCount: 0 })).toBe(100);
    expect(nextAdaptiveBoost({ currentBoost: 100, autoEnabled: true, playerReviewQuality: "mistake", stablePlyCount: 0 })).toBe(200);
  });

  it("reduces the boost after two stable plies", () => {
    const stableCount = nextStablePlyCount({ currentStablePlyCount: 1, quality: "good", hasDanger: false });
    expect(stableCount).toBe(2);
    expect(nextAdaptiveBoost({ currentBoost: 150, autoEnabled: true, playerReviewQuality: "good", stablePlyCount: stableCount })).toBe(100);
  });

  it("does not adjust twice on the same ply", () => {
    expect(
      nextAdaptiveBoost({
        currentBoost: 100,
        autoEnabled: true,
        playerReviewQuality: "blunder",
        currentPly: 7,
        lastAdjustedPly: 7
      })
    ).toBe(100);
  });

  it("formats a compact label for the control", () => {
    expect(formatEloLabel({ baseElo: 1200, adaptiveBoost: 100, autoEnabled: true })).toBe("Niveau 1200 - Auto +100 - Effectif 1300");
    expect(formatEloLabel({ baseElo: 1200, adaptiveBoost: 100, autoEnabled: false })).toBe("Niveau 1200 - Auto off - Effectif 1200");
  });
});
