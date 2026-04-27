import { describe, expect, it } from "vitest";
import { ELO_STEPS, nearestEloStep } from "./elo";

describe("elo helpers", () => {
  it("uses the exact requested Elo steps", () => {
    expect(ELO_STEPS).toEqual([
      600, 800, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400, 2600, 2800, 3000, 3200
    ]);
  });

  it("finds the nearest Elo step", () => {
    expect(nearestEloStep(1175)).toBe(1200);
    expect(nearestEloStep(3100)).toBe(3000);
  });
});
