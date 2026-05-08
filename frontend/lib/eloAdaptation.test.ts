import { describe, expect, it } from "vitest";
import {
  applyAdaptiveSignal,
  baseEloForProfile,
  effectiveElo,
  freshEloTrendState,
  HUMAN_PROFILE_SETTINGS,
  nextAdaptiveBoost,
  nextStablePlyCount,
  normalizeBaseElo,
  normalizeHumanProfile,
  skillLevelForElo
} from "./eloAdaptation";

describe("eloAdaptation", () => {
  it("clamps and steps base Elo values", () => {
    expect(normalizeBaseElo(421)).toBe(1500);
    expect(normalizeBaseElo(1987)).toBe(2000);
    expect(normalizeBaseElo(3900)).toBe(3000);
    expect(effectiveElo(2950, 400)).toBe(3000);
    expect(effectiveElo(1500, -200)).toBe(1500);
    expect(effectiveElo(2000, 1800)).toBe(3000);
  });

  it("maps Elo to the internal skill level", () => {
    expect(skillLevelForElo(1500)).toBe("beginner");
    expect(skillLevelForElo(1750)).toBe("beginner");
    expect(skillLevelForElo(2000)).toBe("intermediate");
    expect(skillLevelForElo(2550)).toBe("intermediate");
    expect(skillLevelForElo(3000)).toBe("pro");
  });

  it("raises the adaptive boost after a serious mistake without jumping more than 200 Elo", () => {
    expect(nextAdaptiveBoost({ currentBoost: 0, autoEnabled: true, playerReviewQuality: "blunder", stablePlyCount: 0 })).toBe(200);
    expect(nextAdaptiveBoost({ currentBoost: 100, autoEnabled: true, playerReviewQuality: "mistake", stablePlyCount: 0 })).toBe(300);
  });

  it("maps human profiles to their hidden base Elo", () => {
    expect(baseEloForProfile("lambda")).toBe(1500);
    expect(baseEloForProfile("strong")).toBe(2000);
    expect(baseEloForProfile("veryStrong")).toBe(3000);
    expect(HUMAN_PROFILE_SETTINGS.veryStrong.description).toContain("GM pratique");
    expect(HUMAN_PROFILE_SETTINGS.veryStrong.description).toContain("moins machine");
    expect(normalizeHumanProfile("unknown")).toBe("strong");
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
    expect(repeated.boost).toBe(300);
    expect(repeated.appliedDelta).toBe(200);

    const critical = applyAdaptiveSignal({
      currentBoost: repeated.boost,
      pressure: "critical",
      suggestedBoostDelta: 200,
      trend: repeated.trend
    });
    expect(critical.appliedDelta).toBe(200);
  });

  it("does not boost after the player's own move unless the position is critical", () => {
    const ownGoodMove = applyAdaptiveSignal({
      currentBoost: 0,
      pressure: "worse",
      suggestedBoostDelta: 200,
      trend: freshEloTrendState(),
      lastMoveWasPlayer: true
    });
    expect(ownGoodMove.boost).toBe(0);
    expect(ownGoodMove.appliedDelta).toBe(0);

    const ownCriticalPosition = applyAdaptiveSignal({
      currentBoost: 0,
      pressure: "critical",
      suggestedBoostDelta: 200,
      trend: freshEloTrendState(),
      lastMoveWasPlayer: true
    });
    expect(ownCriticalPosition.boost).toBe(200);
    expect(ownCriticalPosition.appliedDelta).toBe(200);
  });

  it("drops only after comfort is confirmed", () => {
    const first = applyAdaptiveSignal({
      currentBoost: 300,
      pressure: "stable",
      suggestedBoostDelta: -50,
      trend: freshEloTrendState()
    });
    expect(first.boost).toBe(300);
    expect(first.appliedDelta).toBe(0);

    const repeated = applyAdaptiveSignal({
      currentBoost: first.boost,
      pressure: "stable",
      suggestedBoostDelta: -50,
      trend: first.trend
    });
    expect(repeated.boost).toBe(250);
    expect(repeated.appliedDelta).toBe(-50);
  });

  it("keeps the hidden boost inside the configured bounds", () => {
    expect(
      applyAdaptiveSignal({
        currentBoost: 1450,
        pressure: "critical",
        suggestedBoostDelta: 200,
        trend: freshEloTrendState()
      }).boost
    ).toBe(1500);
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
