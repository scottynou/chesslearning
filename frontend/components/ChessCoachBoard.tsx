"use client";

import { Chessboard } from "react-chessboard";
import type { CSSProperties } from "react";
import type { Square } from "chess.js";
import type { Orientation } from "@/lib/types";

type BoardMove = {
  from: string;
  to: string;
  color?: string;
};

type ChessCoachBoardProps = {
  fen: string;
  boardWidth: number;
  orientation: Orientation;
  selectedSquare: string | null;
  legalTargets: string[];
  highlightedMove?: BoardMove | null;
  recommendationArrows?: BoardMove[];
  lastMove?: BoardMove | null;
  locked?: boolean;
  thinking?: boolean;
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
  recommendationArrows = [],
  lastMove,
  locked = false,
  thinking = false,
  onDrop,
  onSquareClick
}: ChessCoachBoardProps) {
  const customSquareStyles = buildSquareStyles(selectedSquare, legalTargets, lastMove, highlightedMove);
  const frameClassName = ["coach-board-frame", locked && "is-locked", thinking && "is-thinking"].filter(Boolean).join(" ");
  const customArrows = buildArrows(recommendationArrows, highlightedMove);

  return (
    <div className={frameClassName}>
      <div className="coach-board-canvas">
        <Chessboard
          id="chess-elo-coach-board"
          position={fen}
          boardWidth={boardWidth}
          boardOrientation={orientation}
          animationDuration={220}
          areArrowsAllowed={false}
          arePiecesDraggable={!locked && !thinking}
          onPieceDrop={onDrop}
          onSquareClick={(square) => onSquareClick(square)}
          customSquareStyles={customSquareStyles}
          customArrows={customArrows}
          customBoardStyle={{
            borderRadius: "12px",
            boxShadow: "0 46px 130px rgba(0, 0, 0, 0.52), 0 0 0 1px rgba(247, 239, 224, 0.22), inset 0 0 0 1px rgba(255,255,255,0.08)"
          }}
          customDarkSquareStyle={{ backgroundColor: "#6b6658" }}
          customLightSquareStyle={{ backgroundColor: "#e8dcc5" }}
          customDropSquareStyle={{ boxShadow: "inset 0 0 0 4px rgba(247,239,224,0.58), inset 0 0 28px rgba(231,185,106,0.26)" }}
          customNotationStyle={{
            color: "rgba(3, 5, 10, 0.62)",
            fontSize: "0.62rem",
            fontWeight: 900
          }}
        />
      </div>
    </div>
  );
}

function buildArrows(recommendationArrows: BoardMove[], highlightedMove?: BoardMove | null) {
  const arrows = recommendationArrows.map((move) => [
    move.from as Square,
    move.to as Square,
    move.color ?? "rgba(224, 185, 118, 0.72)"
  ]) as [Square, Square, string][];
  if (highlightedMove && !arrows.some(([from, to]) => from === highlightedMove.from && to === highlightedMove.to)) {
    arrows.push([
      highlightedMove.from as Square,
      highlightedMove.to as Square,
      highlightedMove.color ?? "rgba(224, 185, 118, 0.72)"
    ]);
  }
  return arrows;
}

function buildSquareStyles(selectedSquare: string | null, legalTargets: string[], lastMove?: BoardMove | null, highlightedMove?: BoardMove | null) {
  const styles: Record<string, CSSProperties> = {};

  if (lastMove) {
    styles[lastMove.from] = {
      ...(styles[lastMove.from] ?? {}),
      backgroundImage: "linear-gradient(135deg, rgba(231,185,106,0.34), rgba(247,239,224,0.12))",
      boxShadow: "inset 0 0 0 2px rgba(231,185,106,0.30)"
    };
    styles[lastMove.to] = {
      ...(styles[lastMove.to] ?? {}),
      backgroundImage: "radial-gradient(circle at 50% 50%, rgba(247,239,224,0.32), rgba(231,185,106,0.18) 42%, transparent 68%)",
      boxShadow: "inset 0 0 0 2px rgba(231,185,106,0.34)"
    };
  }

  if (selectedSquare) {
    styles[selectedSquare] = {
      ...(styles[selectedSquare] ?? {}),
      backgroundImage: mergeBackgroundImage(styles[selectedSquare]?.backgroundImage, "linear-gradient(135deg, rgba(231,185,106,0.45), rgba(247,239,224,0.16))"),
      boxShadow: mergeBoxShadow(styles[selectedSquare]?.boxShadow, "inset 0 0 0 4px rgba(247,239,224,0.50), inset 0 0 26px rgba(3,5,10,0.22)")
    };
  }

  for (const square of legalTargets) {
    const current = styles[square] ?? {};
    styles[square as Square] = {
      ...current,
      backgroundImage: mergeBackgroundImage(
        current.backgroundImage,
        "radial-gradient(circle at 50% 50%, rgba(247,239,224,0.88) 0 10%, rgba(231,185,106,0.32) 11% 22%, transparent 23%)"
      )
    };
  }

  if (highlightedMove) {
    styles[highlightedMove.from] = {
      ...(styles[highlightedMove.from] ?? {}),
      boxShadow: mergeBoxShadow(styles[highlightedMove.from]?.boxShadow, "inset 0 0 0 4px rgba(224,185,118,0.72), inset 0 0 30px rgba(224,185,118,0.22)")
    };
    styles[highlightedMove.to] = {
      ...(styles[highlightedMove.to] ?? {}),
      boxShadow: mergeBoxShadow(styles[highlightedMove.to]?.boxShadow, "inset 0 0 0 4px rgba(247,239,224,0.44), inset 0 0 30px rgba(224,185,118,0.26)")
    };
  }

  return styles;
}

function mergeBackgroundImage(current: CSSProperties["backgroundImage"], next: string) {
  return current ? `${next}, ${current}` : next;
}

function mergeBoxShadow(current: CSSProperties["boxShadow"], next: string) {
  return current ? `${current}, ${next}` : next;
}
