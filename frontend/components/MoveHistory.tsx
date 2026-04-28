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
    <section className="panel history-panel">
      <div className="history-head">
        <h2 className="panel-title">Historique</h2>
        <span>{moves.length} coups</span>
      </div>
      <div className="coach-scroll history-scroll">
        {pairs.length === 0 ? (
          <p className="history-empty">Aucun coup joue.</p>
        ) : (
          <div className="history-grid">
            {pairs.map((pair) => (
              <div key={pair.number} className="history-row">
                <span className="history-number">{pair.number}.</span>
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
  if (!move) return <span />;
  const notation = notationFromMove(move);
  return (
    <button type="button" onClick={() => onMoveClick?.(ply, move)} className="history-move">
      <span>{notation.shortLabel}</span>
      <small>
        {notation.san}
        {review ? ` · ${shortQuality(review.quality)}` : ""}
      </small>
    </button>
  );
}

function shortQuality(quality: ReviewMoveResponse["quality"]): string {
  return {
    excellent: "Excellent",
    good: "Bon",
    playable: "Jouable",
    inaccurate: "Imprecis",
    mistake: "Erreur",
    blunder: "Grosse erreur"
  }[quality];
}
