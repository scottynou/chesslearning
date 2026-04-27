"use client";

import { useState } from "react";
import clsx from "clsx";
import { OpeningMiniBoard } from "@/components/OpeningMiniBoard";
import type { StrategyPlan } from "@/lib/types";

type OpeningRepertoirePanelProps = {
  plans: StrategyPlan[];
  selectedPlanId?: string | null;
  onSelect: (planId: string) => void;
  title?: string;
  intro?: string;
  emptyMessage?: string;
};

export function OpeningRepertoirePanel({
  plans,
  selectedPlanId,
  onSelect,
  title = "Choisis ton plan",
  intro = "Clique une ouverture pour commencer. Ouvre le detail seulement si tu veux comprendre le plan avant de jouer.",
  emptyMessage = "Aucun plan disponible pour cette situation."
}: OpeningRepertoirePanelProps) {
  const [expandedPlanId, setExpandedPlanId] = useState<string | null>(null);
  const sortedPlans = [...plans].sort((a, b) => difficultyOrder(a.difficulty) - difficultyOrder(b.difficulty));

  return (
    <section className="grid gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-clay">Ouvertures</p>
          <h2 className="mt-1 text-3xl font-semibold text-night md:text-4xl">{title}</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-neutral-600">{intro}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {sortedPlans.map((plan) => {
          const expanded = expandedPlanId === plan.id;
          return (
            <article
              key={plan.id}
              className={clsx(
                "overflow-hidden rounded-lg border bg-white shadow-sm transition hover:-translate-y-0.5 hover:border-night hover:shadow-soft",
                selectedPlanId === plan.id ? "border-clay" : "border-line"
              )}
            >
              <button type="button" onClick={() => onSelect(plan.id)} className="block w-full text-left">
                <OpeningVisual plan={plan} />
                <div className="p-4">
                  <h3 className="text-2xl font-semibold text-night">{plan.nameFr}</h3>
                  <p className="mt-1 text-sm text-neutral-500">{difficultyLabel(plan.difficulty)}</p>
                </div>
              </button>

              <div className="border-t border-line px-4 py-3">
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setExpandedPlanId(expanded ? null : plan.id);
                  }}
                  className="text-sm font-semibold text-night underline-offset-4 hover:underline"
                  aria-expanded={expanded}
                >
                  {expanded ? "Masquer" : "Comprendre ce plan"}
                </button>
              </div>

              {expanded ? <OpeningDetails plan={plan} /> : null}
            </article>
          );
        })}
      </div>

      {sortedPlans.length === 0 ? <div className="panel text-sm text-neutral-700">{emptyMessage}</div> : null}
    </section>
  );
}

function OpeningVisual({ plan }: { plan: StrategyPlan }) {
  if (plan.heroImage) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={plan.heroImage} alt="" className="aspect-[5/3] w-full object-cover" />;
  }
  return (
    <div className="grid aspect-[5/3] place-items-center bg-[radial-gradient(circle_at_20%_20%,#ffffff_0,#f4efe7_38%,#dfd5c8_100%)] p-6">
      <div className="w-44 max-w-[52%]">
        <OpeningMiniBoard fen={plan.miniBoardFen} />
      </div>
    </div>
  );
}

function OpeningDetails({ plan }: { plan: StrategyPlan }) {
  return (
    <div className="grid gap-4 border-t border-line bg-stone-50 p-4">
      {plan.shortHistory ? (
        <section>
          <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-clay">En bref</h4>
          <p className="mt-2 text-sm leading-6 text-neutral-700">{plan.shortHistory}</p>
        </section>
      ) : null}

      <section>
        <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-clay">Objectif</h4>
        <p className="mt-2 text-sm leading-6 text-neutral-700">{plan.learningGoal ?? plan.beginnerGoal}</p>
      </section>

      <section>
        <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-clay">Ce que tu vas apprendre</h4>
        <ul className="mt-2 grid gap-2 text-sm leading-6 text-neutral-700">
          {(plan.whatYouWillLearn ?? plan.coreIdeas).slice(0, 4).map((idea) => (
            <li key={idea} className="rounded border border-line bg-white px-3 py-2">
              {idea}
            </li>
          ))}
        </ul>
      </section>

      {plan.pieceMissions.length > 0 ? (
        <section>
          <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-clay">Pieces importantes</h4>
          <div className="mt-2 grid gap-2">
            {plan.pieceMissions.slice(0, 3).map((mission) => (
              <p key={`${mission.piece}-${mission.mission}`} className="text-sm leading-6 text-neutral-700">
                <span className="font-semibold text-night">{mission.piece}</span> : {mission.mission}
              </p>
            ))}
          </div>
        </section>
      ) : null}

      {plan.middlegamePlan && plan.middlegamePlan.length > 0 ? (
        <section>
          <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-clay">Apres ouverture</h4>
          <p className="mt-2 text-sm leading-6 text-neutral-700">{plan.middlegamePlan.slice(0, 3).join(" - ")}</p>
        </section>
      ) : null}
    </div>
  );
}

function difficultyLabel(difficulty: StrategyPlan["difficulty"]) {
  return {
    easy: "Facile",
    medium: "Intermediaire",
    hard: "Difficile"
  }[difficulty];
}

function difficultyOrder(difficulty: StrategyPlan["difficulty"]) {
  return {
    easy: 1,
    medium: 2,
    hard: 3
  }[difficulty];
}
