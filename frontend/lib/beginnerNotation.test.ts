import { describe, expect, it } from "vitest";
import { notationFromUci } from "./beginnerNotation";

describe("beginner notation", () => {
  it("converts Nf6 into a beginner label", () => {
    const notation = notationFromUci(
      "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1",
      "g8f6",
      "Nf6"
    );

    expect(notation.beginnerLabel).toBe("♞ Cavalier g8 → f6");
    expect(notation.frenchSan).toBe("Cf6");
  });
});
