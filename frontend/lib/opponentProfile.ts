import type { Move } from "chess.js";

export type OpponentStyle = "neutre" | "agressif" | "solide" | "tactique" | "positionnel";

export type OpponentProfile = {
  movesObserved: number;
  captures: number;
  checks: number;
  castled: boolean;
  pawnMoves: number;
  pieceMoves: number;
  earlyQueen: boolean;
  style: OpponentStyle;
  description: string;
};

/**
 * Estime le style de l'adversaire a partir de ses coups joues.
 * Cote frontend on n'a pas l'eval Stockfish des coups adverses, donc on
 * deduit le style a partir de signaux directs : captures, echecs, type
 * de pieces deplacees, roque, sorties precoces de dame.
 */
export function profileOpponent(history: Move[], opponentColor: "w" | "b"): OpponentProfile {
  let captures = 0;
  let checks = 0;
  let castled = false;
  let pawnMoves = 0;
  let pieceMoves = 0;
  let earlyQueen = false;

  history.forEach((move, index) => {
    if (move.color !== opponentColor) return;
    if (move.captured) captures += 1;
    if (move.san.includes("+") || move.san.includes("#")) checks += 1;
    if (move.flags.includes("k") || move.flags.includes("q")) castled = true;
    if (move.piece === "p") pawnMoves += 1;
    else pieceMoves += 1;
    if (move.piece === "q" && Math.floor(index / 2) < 6) earlyQueen = true;
  });

  const movesObserved = history.filter((m) => m.color === opponentColor).length;
  const style = inferStyle({
    movesObserved,
    captures,
    checks,
    castled,
    pawnMoves,
    pieceMoves,
    earlyQueen
  });

  return {
    movesObserved,
    captures,
    checks,
    castled,
    pawnMoves,
    pieceMoves,
    earlyQueen,
    style,
    description: describeStyle(style, captures, checks, castled, movesObserved)
  };
}

function inferStyle(stats: {
  movesObserved: number;
  captures: number;
  checks: number;
  castled: boolean;
  pawnMoves: number;
  pieceMoves: number;
  earlyQueen: boolean;
}): OpponentStyle {
  if (stats.movesObserved < 4) return "neutre";
  const captureRate = stats.captures / stats.movesObserved;
  const checkRate = stats.checks / stats.movesObserved;
  const pawnRatio = stats.pawnMoves / Math.max(1, stats.movesObserved);
  if (checkRate >= 0.18 || (captureRate >= 0.25 && stats.earlyQueen)) return "agressif";
  if (captureRate >= 0.2) return "tactique";
  if (stats.castled && pawnRatio <= 0.35 && checkRate < 0.05) return "solide";
  if (pawnRatio >= 0.45) return "positionnel";
  return "neutre";
}

function describeStyle(style: OpponentStyle, captures: number, checks: number, castled: boolean, observed: number): string {
  if (observed < 4) return "Trop tot pour deviner son style.";
  if (style === "agressif") return `Joue offensivement (${checks} echec(s), ${captures} prise(s)). Sois prudent sur les flancs ouverts.`;
  if (style === "tactique") return `Cherche les complications (${captures} prise(s)). Verifie chaque coup forcé.`;
  if (style === "solide") return castled ? "Roque tot, peu de complications. Joue patient." : "Style retenu, joue patient.";
  if (style === "positionnel") return "Joue les pions, manoeuvre lentement. Anticipe les plans long-terme.";
  return "Style equilibre, pas de signal fort.";
}
