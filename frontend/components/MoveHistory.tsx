"use client";

import type { Move } from "chess.js";
import { notationFromMove } from "@/lib/beginnerNotation";
import type { ReviewMoveResponse } from "@/lib/types";

type MoveHistoryProps = {
  moves: Move[];
  reviews?: Record<number, ReviewMoveResponse>;
  onMoveClick?: (ply: number, move: Move) => void;
};

export function MoveHistory({ moves, reviews = {}, onMoveClick }: MoveHistoryProps) {
  const pairs: Array<{ number: number; white?: Move; black?: Move; whitePly: number; blackPly: number }> = [];
  for (let index = 0; index < moves.length; index += 2) {
    pairs.push({
      number: index / 2 + 1,
      white: moves[index],
      black: moves[index + 1],
      whitePly: index + 1,
      blackPly: index + 2
    });
  }

  return (
    <section className="panel">
      <h2 className="panel-title">Historique</h2>
      <div className="coach-scroll max-h-40 overflow-auto text-sm">
        {pairs.length === 0 ? (
          <p className="text-neutral-500">Aucun coup joué.</p>
        ) : (
          <div className="grid gap-1">
            {pairs.map((pair) => (
              <div key={pair.number} className="grid grid-cols-[2.5rem_1fr_1fr] gap-2 rounded bg-stone-50 px-2 py-1">
                <span className="text-neutral-500">{pair.number}.</span>
                <HistoryMove move={pair.white} ply={pair.whitePly} review={reviews[pair.whitePly]} onMoveClick={onMoveClick} />
                <HistoryMove move={pair.black} ply={pair.blackPly} review={reviews[pair.blackPly]} onMoveClick={onMoveClick} />
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function HistoryMove({
  move,
  ply,
  review,
  onMoveClick
}: {
  move?: Move;
  ply: number;
  review?: ReviewMoveResponse;
  onMoveClick?: (ply: number, move: Move) => void;
}) {
  if (!move) {
    return <span />;
  }
  const notation = notationFromMove(move);
  return (
    <button type="button" onClick={() => onMoveClick?.(ply, move)} className="grid rounded px-1 py-1 text-left hover:bg-white">
      <span className="text-sm font-medium text-night">{notation.shortLabel}</span>
      <span className="text-[11px] text-neutral-500">
        {notation.san}
        {review ? ` · ${shortQuality(review.quality)}` : ""}
      </span>
    </button>
  );
}

function shortQuality(quality: ReviewMoveResponse["quality"]): string {
  return {
    excellent: "Excellent",
    good: "Bon",
    playable: "Jouable",
    inaccurate: "Imprécis",
    mistake: "Erreur",
    blunder: "Grosse erreur"
  }[quality];
}
