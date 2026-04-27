"use client";

import { Chessboard } from "react-chessboard";
import type { CSSProperties } from "react";
import type { Square } from "chess.js";
import type { Orientation } from "@/lib/types";

type ChessCoachBoardProps = {
  fen: string;
  boardWidth: number;
  orientation: Orientation;
  selectedSquare: string | null;
  legalTargets: string[];
  highlightedMove?: { from: string; to: string } | null;
  onDrop: (source: string, target: string) => boolean;
  onSquareClick: (square: string) => void;
};

export function ChessCoachBoard({
  fen,
  boardWidth,
  orientation,
  selectedSquare,
  legalTargets,
  highlightedMove,
  onDrop,
  onSquareClick
}: ChessCoachBoardProps) {
  const customSquareStyles = buildSquareStyles(selectedSquare, legalTargets, highlightedMove);

  return (
    <div className="coach-board-frame">
      <div className="coach-board-frame-top">
        <span>Echiquier interne</span>
        <span>{orientation === "white" ? "Blancs en bas" : "Noirs en bas"}</span>
      </div>
      <div className="coach-board-canvas">
        <Chessboard
          id="chess-elo-coach-board"
          position={fen}
          boardWidth={boardWidth}
          boardOrientation={orientation}
          onPieceDrop={onDrop}
          onSquareClick={(square) => onSquareClick(square)}
          customSquareStyles={customSquareStyles}
          customArrows={highlightedMove ? [[highlightedMove.from as Square, highlightedMove.to as Square, "rgba(185, 103, 69, 0.88)"]] : []}
          customBoardStyle={{
            borderRadius: "10px",
            boxShadow: "0 20px 70px rgba(22, 22, 22, 0.18)"
          }}
          customDarkSquareStyle={{ backgroundColor: "#768b70" }}
          customLightSquareStyle={{ backgroundColor: "#efe1c8" }}
        />
      </div>
    </div>
  );
}

function buildSquareStyles(selectedSquare: string | null, legalTargets: string[], highlightedMove?: { from: string; to: string } | null) {
  const styles: Record<string, CSSProperties> = {};
  if (selectedSquare) {
    styles[selectedSquare] = { background: "rgba(185, 103, 69, 0.55)" };
  }
  for (const square of legalTargets) {
    styles[square as Square] = {
      background:
        "radial-gradient(circle, rgba(39,49,63,0.35) 18%, transparent 20%)"
    };
  }
  if (highlightedMove) {
    styles[highlightedMove.from] = { ...(styles[highlightedMove.from] ?? {}), boxShadow: "inset 0 0 0 4px rgba(185,103,69,0.75)" };
    styles[highlightedMove.to] = { ...(styles[highlightedMove.to] ?? {}), boxShadow: "inset 0 0 0 4px rgba(39,49,63,0.65)" };
  }
  return styles;
}
