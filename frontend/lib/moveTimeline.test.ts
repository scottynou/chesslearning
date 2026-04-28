import { describe, expect, it } from "vitest";
import { canStepBack, redoTimeline, undoTimeline, type MoveSource, type TimelineMove } from "./moveTimeline";

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

  it("undoes exactly one ply per call and queues redo moves in the right order", () => {
    const history = ["e2e4", "e7e5", "g1f3"];
    const sources: MoveSource[] = ["manual", "bot", "manual"];
    const redo: TimelineMove[] = [];

    const firstUndo = undoTimeline(history, sources, redo);
    expect(firstUndo.historyUci).toEqual(["e2e4", "e7e5"]);
    expect(firstUndo.redoStack.map((move) => move.moveUci)).toEqual(["g1f3"]);

    const secondUndo = undoTimeline(firstUndo.historyUci, firstUndo.moveSources, firstUndo.redoStack);
    expect(secondUndo.historyUci).toEqual(["e2e4"]);
    expect(secondUndo.redoStack.map((move) => move.moveUci)).toEqual(["e7e5", "g1f3"]);
  });

  it("redoes exactly one ply per call in the original order", () => {
    const redo: TimelineMove[] = [
      { moveUci: "e7e5", source: "bot" },
      { moveUci: "g1f3", source: "manual" }
    ];

    const firstRedo = redoTimeline(redo);
    expect(firstRedo.nextMove).toEqual({ moveUci: "e7e5", source: "bot" });
    expect(firstRedo.redoStack.map((move) => move.moveUci)).toEqual(["g1f3"]);

    const secondRedo = redoTimeline(firstRedo.redoStack);
    expect(secondRedo.nextMove).toEqual({ moveUci: "g1f3", source: "manual" });
    expect(secondRedo.redoStack).toEqual([]);
  });
});
