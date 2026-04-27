"use client";

import type { PositionPlanResponse } from "@/lib/types";

export function StrategyPanel({ plan }: { plan?: PositionPlanResponse | null }) {
  if (!plan) {
    return null;
  }
  return (
    <section className="panel">
      <h2 className="panel-title">Stratégie globale</h2>
      <div className="grid gap-2 text-sm text-neutral-700">
        <p>{plan.positionContext.centerPawns}</p>
        <p>{plan.positionContext.kingSafety}</p>
        <p>Cases importantes : {plan.positionContext.importantSquares.join(", ")}</p>
        {plan.positionContext.undevelopedPieces.length > 0 ? (
          <p>Pièces à développer : {plan.positionContext.undevelopedPieces.join(", ")}</p>
        ) : null}
      </div>
    </section>
  );
}
