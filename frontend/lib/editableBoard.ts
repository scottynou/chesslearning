import { Chess } from "chess.js";

export const EDITABLE_FILES = ["a", "b", "c", "d", "e", "f", "g", "h"] as const;
export const EDITABLE_RANKS = ["8", "7", "6", "5", "4", "3", "2", "1"] as const;

export type EditablePiece = "K" | "Q" | "R" | "B" | "N" | "P" | "k" | "q" | "r" | "b" | "n" | "p";
export type EditableBoard = Record<string, EditablePiece | null>;

const PIECE_SYMBOLS: Record<EditablePiece, string> = {
  K: "♔",
  Q: "♕",
  R: "♖",
  B: "♗",
  N: "♘",
  P: "♙",
  k: "♚",
  q: "♛",
  r: "♜",
  b: "♝",
  n: "♞",
  p: "♟"
};

const PIECE_LABELS: Record<EditablePiece, string> = {
  K: "Roi blanc",
  Q: "Dame blanche",
  R: "Tour blanche",
  B: "Fou blanc",
  N: "Cavalier blanc",
  P: "Pion blanc",
  k: "Roi noir",
  q: "Dame noire",
  r: "Tour noire",
  b: "Fou noir",
  n: "Cavalier noir",
  p: "Pion noir"
};

export function pieceSymbol(piece: EditablePiece | null): string {
  if (!piece) return "";
  return PIECE_SYMBOLS[piece] ?? "?";
}

export function pieceLabel(piece: EditablePiece): string {
  return PIECE_LABELS[piece] ?? piece;
}

export function emptyEditableBoard(): EditableBoard {
  const board: EditableBoard = {};
  for (const rank of EDITABLE_RANKS) {
    for (const file of EDITABLE_FILES) {
      board[`${file}${rank}`] = null;
    }
  }
  return board;
}

export function editableBoardFromFen(fen: string): EditableBoard {
  const board = emptyEditableBoard();
  const placement = fen.split(" ")[0] || "8/8/8/8/8/8/8/8";
  const rows = placement.split("/");
  rows.forEach((row, rowIndex) => {
    const rank = String(8 - rowIndex);
    let fileIndex = 0;
    for (const char of row) {
      const emptyCount = Number(char);
      if (Number.isInteger(emptyCount) && emptyCount > 0) {
        fileIndex += emptyCount;
        continue;
      }
      const file = EDITABLE_FILES[fileIndex];
      if (file && isEditablePiece(char)) {
        board[`${file}${rank}`] = char;
      }
      fileIndex += 1;
    }
  });
  return board;
}

export function editableBoardToFen(
  board: EditableBoard,
  sideToMove: "white" | "black",
  castling: string = "-",
  enPassant: string = "-"
): string {
  const rows = EDITABLE_RANKS.map((rank) => {
    let row = "";
    let empty = 0;
    for (const file of EDITABLE_FILES) {
      const piece = board[`${file}${rank}`];
      if (!piece) {
        empty += 1;
      } else {
        if (empty) row += String(empty);
        row += piece;
        empty = 0;
      }
    }
    if (empty) row += String(empty);
    return row || "8";
  });
  return `${rows.join("/")} ${sideToMove === "white" ? "w" : "b"} ${castling} ${enPassant} 0 1`;
}

export function editableBoardIsLegalForChess(
  board: EditableBoard,
  sideToMove: "white" | "black",
  castling: string = "-"
): boolean {
  try {
    new Chess(editableBoardToFen(board, sideToMove, castling));
    return true;
  } catch {
    return false;
  }
}

export function isEditablePiece(value: string): value is EditablePiece {
  return ["K", "Q", "R", "B", "N", "P", "k", "q", "r", "b", "n", "p"].includes(value);
}

export function inferCastlingRights(board: EditableBoard): string {
  // Reconstruit "KQkq" pour les rois et tours encore sur cases de depart.
  let rights = "";
  if (board["e1"] === "K") {
    if (board["h1"] === "R") rights += "K";
    if (board["a1"] === "R") rights += "Q";
  }
  if (board["e8"] === "k") {
    if (board["h8"] === "r") rights += "k";
    if (board["a8"] === "r") rights += "q";
  }
  return rights || "-";
}
