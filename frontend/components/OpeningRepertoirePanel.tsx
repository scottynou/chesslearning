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
  const isBlackReply = mode === "black-reply";

  return (
    <section className="repertoire-shell">
      <div className="repertoire-intro">
        <div>
          <p className="repertoire-kicker">{isBlackReply ? "Repertoire noir adapte" : "Repertoire blanc"}</p>
          <h2 className="repertoire-title">{title}</h2>
        </div>
        <div className="repertoire-intro-copy">
          {firstMoveLabel ? <span className="repertoire-context-chip">Premier coup blanc : {firstMoveLabel}</span> : null}
          <p>{intro}</p>
        </div>
      </div>

      <div className="repertoire-grid">
        {sortedPlans.map((plan) => {
          const expanded = expandedPlanIds.includes(plan.id);
          return (
            <PlanCard
              key={plan.id}
              plan={plan}
              selected={selectedPlanId === plan.id}
              expanded={expanded}
              mode={mode}
              firstMoveLabel={firstMoveLabel}
              onSelect={onSelect}
              onToggleDetails={() => {
                setExpandedPlanIds((current) => (expanded ? current.filter((id) => id !== plan.id) : [...current, plan.id]));
              }}
            />
          );
        })}
      </div>

      {sortedPlans.length === 0 ? <div className="panel text-sm text-neutral-700">{emptyMessage}</div> : null}
    </section>
  );
}

function PlanCard({
  plan,
  selected,
  expanded,
  mode,
  firstMoveLabel,
  onSelect,
  onToggleDetails
}: {
  plan: StrategyPlan;
  selected: boolean;
  expanded: boolean;
  mode: "opening" | "black-reply";
  firstMoveLabel?: string | null;
  onSelect: (planId: string) => void;
  onToggleDetails: () => void;
}) {
  const isBlackReply = mode === "black-reply";
  const lead = isBlackReply ? blackReplyReason(plan, firstMoveLabel) : plan.shortHistory ?? plan.learningGoal ?? plan.beginnerGoal;
  const primaryIdea = plan.learningGoal ?? plan.beginnerGoal;

  return (
    <article className={clsx("opening-card", selected && "is-selected", isBlackReply && "is-black-reply")}>
      <button type="button" onClick={() => onSelect(plan.id)} className="opening-card-main">
        <OpeningVisual plan={plan} side={isBlackReply ? "black" : "white"} />

        <div className="opening-card-body">
          <div className="opening-card-topline">
            <span>{difficultyLabel(plan.difficulty)}</span>
            <span>{tierLabel(plan.tier)}</span>
          </div>

          <h3 className="opening-card-title">{plan.nameFr}</h3>

          <p className="opening-card-summary">{lead}</p>

          <div className="opening-style-row">
            {plan.style.slice(0, 3).map((style) => (
              <span key={style}>{style}</span>
            ))}
          </div>

          <div className="opening-primary-goal">
            <strong>{isBlackReply ? "Pourquoi ici" : "Objectif"}</strong>
            <p>{primaryIdea}</p>
          </div>
        </div>
      </button>

      <div className="opening-card-actions">
        <button type="button" onClick={onToggleDetails} className="opening-detail-toggle" aria-expanded={expanded}>
          {expanded ? "Masquer" : isBlackReply ? "Comprendre cette reponse" : "Comprendre ce plan"}
        </button>
        <span>{mainLinePreview(plan)}</span>
      </div>

      {expanded ? <OpeningDetails plan={plan} mode={mode} firstMoveLabel={firstMoveLabel} /> : null}
    </article>
  );
}

function OpeningVisual({ plan, side }: { plan: StrategyPlan; side: "white" | "black" }) {
  if (plan.heroImage) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={plan.heroImage} alt="" className="opening-hero-image" />;
  }
  return (
    <div className={clsx("opening-visual", side === "black" && "is-black")}>
      <div className="opening-visual-grid" />
      <div className="opening-visual-board">
        <OpeningMiniBoard fen={plan.miniBoardFen} />
      </div>
      <div className="opening-visual-caption">
        <span>{side === "black" ? "Reponse" : "Plan"}</span>
        <strong>{plan.eco.slice(0, 2).join(" / ") || "Guide"}</strong>
      </div>
    </div>
  );
}

function OpeningDetails({ plan, mode, firstMoveLabel }: { plan: StrategyPlan; mode: "opening" | "black-reply"; firstMoveLabel?: string | null }) {
  const ideas = (plan.whatYouWillLearn ?? plan.coreIdeas).slice(0, 5);
  const missions = plan.pieceMissions.slice(0, 4);
  const isBlackReply = mode === "black-reply";

  return (
    <div className="opening-details">
      <section className="opening-detail-block is-wide">
        <h4>{isBlackReply ? "Pourquoi cette reponse marche" : "En clair"}</h4>
        <p>{isBlackReply ? blackReplyReason(plan, firstMoveLabel) : plan.shortHistory ?? plan.learningGoal ?? plan.beginnerGoal}</p>
      </section>

      <section className="opening-detail-block">
        <h4>Ce que tu vas apprendre</h4>
        <ul className="opening-learning-list">
          {ideas.map((idea) => (
            <li key={idea}>{idea}</li>
          ))}
        </ul>
      </section>

      <section className="opening-detail-block">
        <h4>Pieces importantes</h4>
        {missions.length > 0 ? (
          <div className="opening-mission-list">
            {missions.map((mission) => (
              <p key={`${mission.piece}-${mission.mission}`}>
                <strong>{mission.piece}</strong> : {mission.mission}
              </p>
            ))}
          </div>
        ) : (
          <p>Le plan se concentre surtout sur le centre, le developpement et la securite du roi.</p>
        )}
      </section>

      {plan.middlegamePlan && plan.middlegamePlan.length > 0 ? (
        <section className="opening-detail-block is-wide">
          <h4>Apres l&apos;ouverture</h4>
          <p>{plan.middlegamePlan.slice(0, 3).join(" - ")}</p>
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

function tierLabel(tier: StrategyPlan["tier"]) {
  return {
    recommended: "Recommande",
    good: "Bon choix",
    situational: "Situationnel",
    hidden: "Labo"
  }[tier];
}

function mainLinePreview(plan: StrategyPlan) {
  if (!plan.mainLineUci.length) return "Plan general";
  return `${plan.mainLineUci.length} coups guides`;
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
