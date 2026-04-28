import { describe, expect, it } from "vitest";
import { canStepBack, redoTimeline, undoTimeline } from "./moveTimeline";

describe("move timeline", () => {
  it("moves the last ply into the redo stack and preserves its source", () => {
    const result = undoTimeline(["e2e4", "c7c6", "d2d4"], ["manual", "bot", "manual"], []);

    expect(result.historyUci).toEqual(["e2e4", "c7c6"]);
    expect(result.moveSources).toEqual(["manual", "bot"]);
    expect(result.redoStack).toEqual([{ moveUci: "d2d4", source: "manual" }]);
  });

  it("protects the first black-repertoire ply from being removed", () => {
    expect(canStepBack(1, 1)).toBe(false);

    const result = undoTimeline(["e2e4"], ["manual"], [], 1);
    expect(result.undoneMove).toBeNull();
    expect(result.historyUci).toEqual(["e2e4"]);
  });

  it("pops the next redo move", () => {
    const result = redoTimeline([
      { moveUci: "d2d4", source: "manual" },
      { moveUci: "d7d5", source: "bot" }
    ]);

    expect(result.nextMove).toEqual({ moveUci: "d2d4", source: "manual" });
    expect(result.redoStack).toEqual([{ moveUci: "d7d5", source: "bot" }]);
  });
});
