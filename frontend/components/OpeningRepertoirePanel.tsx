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
  mode?: "opening" | "black-reply";
  firstMoveLabel?: string | null;
};

export function OpeningRepertoirePanel({
  plans,
  selectedPlanId,
  onSelect,
  title = "Choisis ton plan",
  intro = "Clique une ouverture pour commencer. Ouvre le detail seulement si tu veux comprendre le plan avant de jouer.",
  emptyMessage = "Aucun plan disponible pour cette situation.",
  mode = "opening",
  firstMoveLabel
}: OpeningRepertoirePanelProps) {
  const [expandedPlanIds, setExpandedPlanIds] = useState<string[]>([]);
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
          const expanded = expandedPlanIds.includes(plan.id);
          if (mode === "black-reply") {
            return (
              <BlackReplyCard
                key={plan.id}
                plan={plan}
                selected={selectedPlanId === plan.id}
                firstMoveLabel={firstMoveLabel}
                onSelect={onSelect}
              />
            );
          }

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
                    setExpandedPlanIds((current) => (expanded ? current.filter((id) => id !== plan.id) : [...current, plan.id]));
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

function BlackReplyCard({
  plan,
  selected,
  firstMoveLabel,
  onSelect
}: {
  plan: StrategyPlan;
  selected: boolean;
  firstMoveLabel?: string | null;
  onSelect: (planId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(plan.id)}
      className={clsx(
        "grid min-h-56 content-between rounded-lg border bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-night hover:shadow-soft",
        selected ? "border-clay" : "border-line"
      )}
    >
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-clay">Reponse noire</p>
        <h3 className="mt-2 text-2xl font-semibold text-night">{plan.nameFr}</h3>
        <p className="mt-4 text-sm font-semibold text-neutral-500">Pourquoi cette option est coherente{firstMoveLabel ? ` apres ${firstMoveLabel}` : ""}</p>
        <p className="mt-2 text-sm leading-6 text-neutral-700">{blackReplyReason(plan, firstMoveLabel)}</p>
      </div>
      <p className="mt-5 text-sm font-semibold text-night">Choisir ce plan</p>
    </button>
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

function blackReplyReason(plan: StrategyPlan, firstMoveLabel?: string | null) {
  const firstMoveContext = firstMoveLabel ? `Les blancs commencent par ${firstMoveLabel}. ` : "";
  const known: Record<string, string> = {
    black_e5_classical:
      "Tu reponds directement au centre avec le pion e. C'est le choix le plus classique pour apprendre les positions ouvertes : les cavaliers sortent vite, les pieces se developpent naturellement et le roi peut roquer assez tot.",
    caro_kann_beginner:
      "Tu construis une position solide avant d'attaquer le centre avec le pion d. C'est une bonne option si tu veux un milieu de partie clair, avec moins de tactiques immediates que certaines defenses plus agressives.",
    french_defense_beginner:
      "Tu prepares ...d5 avec une structure compacte. Ce plan est utile si tu veux apprendre les centres fermes : les blancs prennent souvent de l'espace, puis tu attaques leur chaine de pions.",
    scandinavian_simple:
      "Tu attaques tout de suite le centre. C'est simple a comprendre : les noirs refusent de laisser les blancs installer e4 tranquillement, mais il faudra developper vite ensuite.",
    sicilian_dragon_simplified:
      "Tu choisis une reponse active avec le pion c. Le plan vise a contester le centre depuis le cote et a placer le fou en g7, mais il demande plus de precision.",
    qgd_simplified:
      "Tu reponds au pion dame par une structure tres stable. Ce plan garde le centre solide, developpe les pieces sans urgence et donne un milieu de partie facile a lire.",
    slav_beginner:
      "Tu soutiens le pion d avec le pion c. L'idee est de garder le centre solide tout en laissant le fou c8 respirer, ce qui rend la suite plus naturelle.",
    kings_indian_setup:
      "Tu acceptes que les blancs prennent le centre au debut, puis tu prepares une contre-attaque apres le roque. C'est flexible, mais plus strategique."
  };
  return `${firstMoveContext}${known[plan.id] ?? plan.learningGoal ?? plan.beginnerGoal}`;
}
