import { Chess, Move, Square } from "chess.js";
import type { CandidateMove } from "./types";

const PIECE_NAMES: Record<string, string> = {
  p: "Pion",
  n: "Cavalier",
  b: "Fou",
  r: "Tour",
  q: "Dame",
  k: "Roi"
};

const PIECE_ICONS: Record<string, string> = {
  wp: "♙",
  wn: "♘",
  wb: "♗",
  wr: "♖",
  wq: "♕",
  wk: "♔",
  bp: "♟",
  bn: "♞",
  bb: "♝",
  br: "♜",
  bq: "♛",
  bk: "♚"
};

const FRENCH_SAN: Record<string, string> = {
  N: "C",
  B: "F",
  R: "T",
  Q: "D",
  K: "R"
};

export type BeginnerNotation = {
  beginnerLabel: string;
  shortLabel: string;
  san: string;
  frenchSan: string;
  uci: string;
  pieceName: string;
  from: string;
  to: string;
  icon: string;
};

export function notationFromCandidate(fen: string, candidate: CandidateMove): BeginnerNotation {
  return notationFromUci(fen, candidate.moveUci, candidate.moveSan);
}

export function notationFromMove(move: Move): BeginnerNotation {
  const pieceName = PIECE_NAMES[move.piece] ?? "Pièce";
  const icon = PIECE_ICONS[`${move.color}${move.piece}`] ?? "•";
  const isCastling = move.san.startsWith("O-O");
  const beginnerLabel = isCastling
    ? `${move.san.startsWith("O-O-O") ? "Grand" : "Petit"} roque : le roi se met en sécurité`
    : `${icon} ${pieceName} ${move.from} → ${move.to}`;

  return {
    beginnerLabel,
    shortLabel: isCastling ? beginnerLabel.split(" : ")[0] : `${pieceName} → ${move.to}`,
    san: move.san,
    frenchSan: frenchSan(move.san),
    uci: `${move.from}${move.to}${move.promotion ?? ""}`,
    pieceName,
    from: move.from,
    to: move.to,
    icon
  };
}

export function notationFromUci(fen: string, uci: string, san?: string): BeginnerNotation {
  const game = new Chess(fen);
  const from = uci.slice(0, 2);
  const to = uci.slice(2, 4);
  const promotion = uci.slice(4);
  const piece = game.get(from as Square);
  const pieceName = piece ? PIECE_NAMES[piece.type] : "Pièce";
  const icon = piece ? PIECE_ICONS[`${piece.color}${piece.type}`] : "•";
  let moveSan = san ?? uci;

  try {
    const move = game.move({ from, to, ...(promotion ? { promotion } : {}) });
    if (move) {
      moveSan = san ?? move.san;
    }
  } catch {
    moveSan = san ?? uci;
  }

  const isCastling = moveSan.startsWith("O-O");
  const beginnerLabel = isCastling
    ? `${moveSan.startsWith("O-O-O") ? "Grand" : "Petit"} roque : le roi se met en sécurité`
    : `${icon} ${pieceName} ${from} → ${to}`;

  return {
    beginnerLabel,
    shortLabel: isCastling ? beginnerLabel.split(" : ")[0] : `${pieceName} → ${to}`,
    san: moveSan,
    frenchSan: frenchSan(moveSan),
    uci,
    pieceName,
    from,
    to,
    icon
  };
}

export function frenchSan(san: string): string {
  if (!san || san.startsWith("O-O")) {
    return san;
  }
  return `${FRENCH_SAN[san[0]] ?? san[0]}${san.slice(1)}`;
}
