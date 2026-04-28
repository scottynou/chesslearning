import { describe, expect, it } from "vitest";
import { Chess } from "chess.js";
import { canMoveInMode, gameStatus, isPromotionAttempt, tryMove } from "./chess";

describe("chess helpers", () => {
  it("accepts legal moves", () => {
    const result = tryMove(new Chess(), "e2", "e4");
    expect(result?.move.san).toBe("e4");
  });

  it("rejects illegal moves", () => {
    const result = tryMove(new Chess(), "e2", "e5");
    expect(result).toBeNull();
  });

  it("detects mode permissions", () => {
    const game = new Chess();
    expect(canMoveInMode(game, "both")).toBe(true);
    expect(canMoveInMode(game, "white")).toBe(true);
    expect(canMoveInMode(game, "black")).toBe(false);
  });

  it("detects promotion attempts", () => {
    const game = new Chess("8/P7/8/8/8/8/8/4k2K w - - 0 1");
    expect(isPromotionAttempt(game, "a7", "a8")).toBe(true);
  });

  it("reports checkmate positions", () => {
    const game = new Chess("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3");
    expect(game.isCheckmate()).toBe(true);
    expect(gameStatus(game)).toBe("Mat");
  });
});
