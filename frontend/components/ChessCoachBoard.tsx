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
  const customSquareStyles = buildSquareStyles(selectedSquare, legalTargets, lastMove, recommendationArrows, highlightedMove);
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
            borderRadius: "8px",
            boxShadow: "0 46px 130px rgba(0, 0, 0, 0.56), 0 0 0 1px rgba(247, 239, 224, 0.24), inset 0 0 0 1px rgba(255,255,255,0.08)"
          }}
          customDarkSquareStyle={{ backgroundColor: "#625f52" }}
          customLightSquareStyle={{ backgroundColor: "#eadfc8" }}
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

function buildSquareStyles(
  selectedSquare: string | null,
  legalTargets: string[],
  lastMove?: BoardMove | null,
  recommendationArrows: BoardMove[] = [],
  highlightedMove?: BoardMove | null
) {
  const styles: Record<string, CSSProperties> = {};

  if (lastMove) {
    styles[lastMove.from] = {
      ...(styles[lastMove.from] ?? {}),
      backgroundImage: "linear-gradient(135deg, rgba(247,239,224,0.18), rgba(247,239,224,0.05))",
      boxShadow: "inset 0 0 0 2px rgba(247,239,224,0.20)"
    };
    styles[lastMove.to] = {
      ...(styles[lastMove.to] ?? {}),
      backgroundImage: "radial-gradient(circle at 50% 50%, rgba(247,239,224,0.26), rgba(247,239,224,0.10) 42%, transparent 68%)",
      boxShadow: "inset 0 0 0 2px rgba(247,239,224,0.24)"
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

  for (const move of recommendationArrows) {
    applyMoveGlow(styles, move);
  }

  if (highlightedMove) {
    applyMoveGlow(styles, highlightedMove, true);
  }

  return styles;
}

function applyMoveGlow(styles: Record<string, CSSProperties>, move: BoardMove, focused = false) {
  const color = move.color ?? "rgba(224,185,118,0.78)";
  const fromGlow = colorWithAlpha(color, focused ? 0.30 : 0.18);
  const fromBorder = colorWithAlpha(color, focused ? 0.58 : 0.36);
  const toGlow = colorWithAlpha(color, focused ? 0.42 : 0.30);
  const toBorder = colorWithAlpha(color, focused ? 0.78 : 0.62);

  styles[move.from] = {
    ...(styles[move.from] ?? {}),
    backgroundImage: mergeBackgroundImage(
      styles[move.from]?.backgroundImage,
      `linear-gradient(135deg, ${fromGlow}, transparent 72%)`
    ),
    boxShadow: mergeBoxShadow(styles[move.from]?.boxShadow, `inset 0 0 0 2px ${fromBorder}`)
  };
  styles[move.to] = {
    ...(styles[move.to] ?? {}),
    backgroundImage: mergeBackgroundImage(
      styles[move.to]?.backgroundImage,
      `radial-gradient(circle at 50% 50%, ${toGlow}, transparent 68%)`
    ),
    boxShadow: mergeBoxShadow(
      styles[move.to]?.boxShadow,
      `inset 0 0 0 ${focused ? 5 : 4}px ${toBorder}, inset 0 0 34px ${toGlow}`
    )
  };
}

function colorWithAlpha(color: string, alpha: number) {
  const rgbaMatch = color.match(/^rgba?\(([^)]+)\)$/);
  if (!rgbaMatch) return color;
  const parts = rgbaMatch[1].split(",").map((part) => part.trim());
  if (parts.length < 3) return color;
  return `rgba(${parts[0]}, ${parts[1]}, ${parts[2]}, ${alpha})`;
}

function mergeBackgroundImage(current: CSSProperties["backgroundImage"], next: string) {
  return current ? `${next}, ${current}` : next;
}

function mergeBoxShadow(current: CSSProperties["boxShadow"], next: string) {
  return current ? `${current}, ${next}` : next;
}
