"use client";

import type { PositionPlanResponse } from "@/lib/types";

export function OpeningCoachPanel({ plan }: { plan?: PositionPlanResponse | null }) {
  return (
    <section className="panel">
      <h2 className="panel-title">Plan de partie</h2>
      {!plan ? <p className="text-sm text-neutral-500">Le plan apparaîtra après l&apos;analyse de la position.</p> : null}
      {plan ? (
        <div className="grid gap-3">
          <div className="rounded border border-line bg-stone-50 px-3 py-2">
            <p className="text-xs font-semibold uppercase text-clay">Phase actuelle</p>
            <p className="text-lg font-semibold text-night">{plan.phaseLabel}</p>
          </div>
          {plan.detectedOpening ? (
            <div className="rounded border border-line bg-white px-3 py-2">
              <p className="text-xs font-semibold uppercase text-clay">Ouverture détectée</p>
              <p className="font-semibold text-night">{plan.detectedOpening.name}</p>
              <p className="mt-1 text-sm text-neutral-700">{plan.detectedOpening.beginnerGoal}</p>
            </div>
          ) : null}
          <div>
            <h3 className="text-sm font-semibold text-night">Plan</h3>
            <ol className="mt-2 grid gap-1 text-sm text-neutral-700">
              {plan.plan.map((item, index) => (
                <li key={item}>
                  {index + 1}. {item}
                </li>
              ))}
            </ol>
          </div>
          <div className="rounded border border-line bg-stone-50 px-3 py-2">
            <h3 className="text-sm font-semibold text-night">Prochain objectif</h3>
            <p className="mt-1 text-sm text-neutral-700">{plan.nextObjective}</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
