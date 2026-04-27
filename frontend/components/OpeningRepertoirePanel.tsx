"use client";

import clsx from "clsx";
import { OpeningMiniBoard } from "@/components/OpeningMiniBoard";
import type { StrategyPlan } from "@/lib/types";

type OpeningRepertoirePanelProps = {
  plans: StrategyPlan[];
  selectedPlanId?: string | null;
  onSelect: (planId: string) => void;
};

export function OpeningRepertoirePanel({ plans, selectedPlanId, onSelect }: OpeningRepertoirePanelProps) {
  return (
    <section className="grid gap-4">
      <div>
        <p className="text-sm font-semibold uppercase text-clay">Répertoire guidé</p>
        <h2 className="text-2xl font-bold text-night">Choisis ton plan</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-700">
          Chaque carte est un plan d&apos;apprentissage. Une fois choisi, le coach garde ce fil conducteur et adapte seulement le prochain coup si l&apos;adversaire dévie.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {plans.map((plan) => (
          <button
            key={plan.id}
            type="button"
            onClick={() => onSelect(plan.id)}
            className={clsx(
              "grid overflow-hidden rounded border bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-sage hover:shadow-md",
              selectedPlanId === plan.id ? "border-clay" : "border-line"
            )}
          >
            <OpeningVisual plan={plan} />
            <div className="grid gap-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold text-night">{plan.nameFr}</span>
                <span className="rounded bg-stone-100 px-2 py-1 text-xs text-neutral-700">{tierLabel(plan.tier)}</span>
                <span className="rounded bg-stone-100 px-2 py-1 text-xs text-neutral-700">{difficultyLabel(plan.difficulty)}</span>
              </div>
              <p className="text-sm leading-6 text-neutral-700">{plan.learningGoal ?? plan.beginnerGoal}</p>
              <div>
                <p className="text-xs font-semibold uppercase text-clay">Ce que tu vas apprendre</p>
                <ul className="mt-1 grid gap-1 text-sm text-neutral-700">
                  {(plan.whatYouWillLearn ?? plan.coreIdeas).slice(0, 3).map((idea) => (
                    <li key={idea}>• {idea}</li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-neutral-500">Style : {plan.style.join(", ")}</p>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function OpeningVisual({ plan }: { plan: StrategyPlan }) {
  if (plan.heroImage) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={plan.heroImage} alt="" className="h-36 w-full object-cover" />;
  }
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_96px] items-center gap-3 bg-stone-50 p-4">
      <div>
        <p className="text-xs font-semibold uppercase text-clay">{sideLabel(plan.side)}</p>
        <p className="mt-2 text-sm font-semibold text-night">{plan.shortHistory ?? plan.beginnerGoal}</p>
      </div>
      <OpeningMiniBoard fen={plan.miniBoardFen} />
    </div>
  );
}

function sideLabel(side: StrategyPlan["side"]) {
  return {
    white: "Plan blancs",
    black: "Plan noirs",
    universal: "Plan universel"
  }[side];
}

function tierLabel(tier: StrategyPlan["tier"]) {
  return {
    recommended: "Recommandée",
    good: "Bonne option",
    situational: "Situationnelle",
    hidden: "Laboratoire"
  }[tier];
}

function difficultyLabel(difficulty: StrategyPlan["difficulty"]) {
  return {
    easy: "Facile",
    medium: "Moyenne",
    hard: "Difficile"
  }[difficulty];
}
