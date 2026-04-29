import { describe, expect, it } from "vitest";
import {
  applyAdaptiveSignal,
  effectiveElo,
  freshEloTrendState,
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
    expect(effectiveElo(1200, -200)).toBe(1200);
    expect(effectiveElo(1200, 1800)).toBe(2200);
  });

  it("maps Elo to the internal skill level", () => {
    expect(skillLevelForElo(600)).toBe("beginner");
    expect(skillLevelForElo(1400)).toBe("beginner");
    expect(skillLevelForElo(1450)).toBe("intermediate");
    expect(skillLevelForElo(2350)).toBe("intermediate");
    expect(skillLevelForElo(2400)).toBe("pro");
  });

  it("raises the adaptive boost after a serious mistake without jumping more than 200 Elo", () => {
    expect(nextAdaptiveBoost({ currentBoost: 0, autoEnabled: true, playerReviewQuality: "blunder", stablePlyCount: 0 })).toBe(200);
    expect(nextAdaptiveBoost({ currentBoost: 100, autoEnabled: true, playerReviewQuality: "mistake", stablePlyCount: 0 })).toBe(300);
  });

  it("reduces the hidden adjustment after two stable plies", () => {
    const stableCount = nextStablePlyCount({ currentStablePlyCount: 1, quality: "good", hasDanger: false });
    expect(stableCount).toBe(2);
    expect(nextAdaptiveBoost({ currentBoost: 150, autoEnabled: true, playerReviewQuality: "good", stablePlyCount: stableCount })).toBe(100);
    expect(nextAdaptiveBoost({ currentBoost: 0, autoEnabled: true, playerReviewQuality: "excellent", stablePlyCount: stableCount })).toBe(0);
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

  it("amplifies repeated pressure without exceeding the per-ply cap", () => {
    const first = applyAdaptiveSignal({
      currentBoost: 0,
      pressure: "drawish",
      suggestedBoostDelta: 100,
      trend: freshEloTrendState()
    });
    expect(first.boost).toBe(100);

    const repeated = applyAdaptiveSignal({
      currentBoost: first.boost,
      pressure: "drawish",
      suggestedBoostDelta: 100,
      trend: first.trend
    });
    expect(repeated.boost).toBe(250);
    expect(repeated.appliedDelta).toBe(150);

    const critical = applyAdaptiveSignal({
      currentBoost: repeated.boost,
      pressure: "critical",
      suggestedBoostDelta: 200,
      trend: repeated.trend
    });
    expect(critical.appliedDelta).toBe(200);
  });

  it("drops faster only after comfort is confirmed", () => {
    const first = applyAdaptiveSignal({
      currentBoost: 300,
      pressure: "stable",
      suggestedBoostDelta: -50,
      trend: freshEloTrendState()
    });
    expect(first.boost).toBe(250);

    const repeated = applyAdaptiveSignal({
      currentBoost: first.boost,
      pressure: "stable",
      suggestedBoostDelta: -50,
      trend: first.trend
    });
    expect(repeated.boost).toBe(150);
    expect(repeated.appliedDelta).toBe(-100);
  });

  it("keeps the hidden boost inside the configured bounds", () => {
    expect(
      applyAdaptiveSignal({
        currentBoost: 950,
        pressure: "critical",
        suggestedBoostDelta: 200,
        trend: freshEloTrendState()
      }).boost
    ).toBe(1000);
    expect(
      applyAdaptiveSignal({
        currentBoost: 0,
        pressure: "stable",
        suggestedBoostDelta: -100,
        trend: freshEloTrendState()
      }).boost
    ).toBe(0);
  });

});
