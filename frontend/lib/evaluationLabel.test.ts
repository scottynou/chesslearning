import { describe, expect, it } from "vitest";
import { evaluationLabel } from "./evaluationLabel";

describe("evaluation labels", () => {
  it("converts centipawns into beginner-friendly labels", () => {
    expect(evaluationLabel(-31)).toBe("Léger avantage noir");
    expect(evaluationLabel(24)).toBe("Position équilibrée");
    expect(evaluationLabel(145)).toBe("Avantage clair blanc");
    expect(evaluationLabel(-320)).toBe("Avantage décisif noir");
  });
});
