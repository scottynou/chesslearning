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
  intro = "Choisis une direction simple, le coach s'occupe du reste.",
  emptyMessage = "Aucun plan disponible pour cette situation.",
  mode = "opening",
  firstMoveLabel
}: OpeningRepertoirePanelProps) {
  const sortedPlans = [...plans].sort((a, b) => difficultyOrder(a.difficulty) - difficultyOrder(b.difficulty));

  return (
    <section className="repertoire-shell">
      <div className="repertoire-intro">
        <h2 className="repertoire-title">{title}</h2>
        <div className="repertoire-intro-copy">
          {firstMoveLabel ? <span className="repertoire-context-chip">Premier coup : {firstMoveLabel}</span> : null}
          <p>{intro}</p>
        </div>
      </div>

      <div className="repertoire-grid">
        {sortedPlans.map((plan) => (
          <PlanCard
            key={plan.id}
            plan={plan}
            selected={selectedPlanId === plan.id}
            mode={mode}
            firstMoveLabel={firstMoveLabel}
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
  firstMoveLabel,
  onSelect
}: {
  plan: StrategyPlan;
  selected: boolean;
  mode: "opening" | "black-reply";
  firstMoveLabel?: string | null;
  onSelect: (planId: string) => void;
}) {
  const isBlackReply = mode === "black-reply";
  const lead = compactText(isBlackReply ? blackReplyReason(plan, firstMoveLabel) : plan.shortHistory ?? plan.learningGoal ?? plan.beginnerGoal, 92);

  return (
    <article className={clsx("opening-card", selected && "is-selected", isBlackReply && "is-black-reply")}>
      <button type="button" onClick={() => onSelect(plan.id)} className="opening-card-main">
        <OpeningVisual plan={plan} side={isBlackReply ? "black" : "white"} />

        <div className="opening-card-body">
          <div className="opening-card-topline">
            <span>{difficultyLabel(plan.difficulty)}</span>
          </div>

          <h3 className="opening-card-title">{plan.nameFr}</h3>
          <p className="opening-card-summary">{lead}</p>
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
      <div className="opening-visual-caption">
        <span>{side === "black" ? "Reponse" : "Ouverture"}</span>
        <strong>{plan.eco.slice(0, 2).join(" / ") || "Guide"}</strong>
      </div>
    </div>
  );
}

function difficultyLabel(difficulty: StrategyPlan["difficulty"]) {
  return { easy: "Facile", medium: "Intermediaire", hard: "Difficile" }[difficulty];
}

function difficultyOrder(difficulty: StrategyPlan["difficulty"]) {
  return { easy: 1, medium: 2, hard: 3 }[difficulty];
}

function blackReplyReason(plan: StrategyPlan, firstMoveLabel?: string | null) {
  const lead = firstMoveLabel ? `Apres ${firstMoveLabel}, ` : "";
  const goal = plan.learningGoal ?? plan.beginnerGoal;
  return `${lead}${plan.nameFr} donne une reponse simple : ${goal}`;
}

function compactText(value: string, limit: number) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).replace(/[\s,.;:!?]+\S*$/, "")}...`;
}
