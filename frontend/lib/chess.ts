import { Chess, Move, Square } from "chess.js";
import type { PlayMode } from "./types";

export function canMoveInMode(game: Chess, mode: PlayMode): boolean {
  if (mode === "both" || mode === "friend") {
    return true;
  }
  return game.turn() === (mode === "white" ? "w" : "b");
}

export function isPromotionAttempt(game: Chess, from: string, to: string): boolean {
  const piece = game.get(from as Square);
  if (!piece || piece.type !== "p") {
    return false;
  }

  const targetRank = to[1];
  const fileDistance = Math.abs(from.charCodeAt(0) - to.charCodeAt(0));
  return fileDistance <= 1 && ((piece.color === "w" && targetRank === "8") || (piece.color === "b" && targetRank === "1"));
}

export function tryMove(game: Chess, from: string, to: string, promotion?: string): { game: Chess; move: Move } | null {
  const next = new Chess(game.fen());
  try {
    const move = next.move({
      from,
      to,
      ...(promotion ? { promotion } : {})
    });
    return move ? { game: next, move } : null;
  } catch {
    return null;
  }
}

export function gameStatus(game: Chess): string {
  if (game.isCheckmate()) {
    return "Mat";
  }
  if (game.isStalemate()) {
    return "Pat";
  }
  if (game.isDraw()) {
    return "Nulle";
  }
  if (game.inCheck()) {
    return "Échec";
  }
  return game.turn() === "w" ? "Aux blancs" : "Aux noirs";
}
