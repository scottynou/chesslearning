"use client";

import clsx from "clsx";
import { getOpeningImageSrc } from "@/lib/openingVisuals";
import type { StrategyPlan } from "@/lib/types";

type OpeningRepertoirePanelProps = {
  plans: StrategyPlan[];
  selectedPlanId?: string | null;
  onSelect: (planId: string) => void;
  title?: string;
  intro?: string;
  emptyMessage?: string;
  mode?: "opening" | "black-reply";
  firstMoveLabel?: string | null;
};

export function OpeningRepertoirePanel({
  plans,
  selectedPlanId,
  onSelect,
  title = "Choisis ton plan",
  emptyMessage = "Aucun plan disponible pour cette situation.",
  mode = "opening"
}: OpeningRepertoirePanelProps) {
  const sortedPlans = [...plans].sort((a, b) => difficultyOrder(a.difficulty) - difficultyOrder(b.difficulty));

  return (
    <section className="repertoire-shell">
      <div className="repertoire-intro">
        <h2 className="repertoire-title">{title}</h2>
      </div>

      <div className="repertoire-grid">
        {sortedPlans.map((plan) => (
          <PlanCard
            key={plan.id}
            plan={plan}
            selected={selectedPlanId === plan.id}
            mode={mode}
            onSelect={onSelect}
          />
        ))}
      </div>

      {sortedPlans.length === 0 ? <div className="quiet-alert">{emptyMessage}</div> : null}
    </section>
  );
}

function PlanCard({
  plan,
  selected,
  mode,
  onSelect
}: {
  plan: StrategyPlan;
  selected: boolean;
  mode: "opening" | "black-reply";
  onSelect: (planId: string) => void;
}) {
  const isBlackReply = mode === "black-reply";

  return (
    <article className={clsx("opening-card", selected && "is-selected", isBlackReply && "is-black-reply")}>
      <button type="button" onClick={() => onSelect(plan.id)} className="opening-card-main" aria-label={plan.nameFr}>
        <OpeningVisual plan={plan} side={isBlackReply ? "black" : "white"} />

        <div className="opening-card-body">
          <h3 className="opening-card-title">{plan.nameFr}</h3>
        </div>
      </button>
    </article>
  );
}

function OpeningVisual({ plan, side }: { plan: StrategyPlan; side: "white" | "black" }) {
  const imageSrc = getOpeningImageSrc(plan);

  return (
    <div className={clsx("opening-visual", side === "black" && "is-black")}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={imageSrc} alt="" className="opening-hero-image" />
    </div>
  );
}

function difficultyOrder(difficulty: StrategyPlan["difficulty"]) {
  return { easy: 1, medium: 2, hard: 3 }[difficulty];
}
