"use client";

import type { PlanRecommendation, PlanRecommendationsResponse, StrategyPlan } from "@/lib/types";

type PlanFirstPanelProps = {
  selectedPlan?: StrategyPlan | null;
  recommendations?: PlanRecommendationsResponse | null;
  loading?: boolean;
  error?: string | null;
  highlightedMoveUci?: string | null;
  onToggleRecommendation: (recommendation: PlanRecommendation) => void;
};

export function PlanFirstPanel({
  selectedPlan,
  recommendations,
  loading,
  error,
  highlightedMoveUci,
  onToggleRecommendation
}: PlanFirstPanelProps) {
  const primary = recommendations?.primaryMove ?? recommendations?.planMoves[0] ?? recommendations?.mergedRecommendations[0] ?? null;
  const alternatives = recommendations?.adaptedAlternatives ?? [];
  const progress = recommendations?.planProgress;
  const planName = recommendations?.selectedPlan?.nameFr ?? selectedPlan?.nameFr ?? "Plan general";
  const moves = [primary, ...alternatives].filter(Boolean) as PlanRecommendation[];

  return (
    <section className="panel">
      <div className="grid gap-4">
        <div>
          <p className="text-xs font-semibold uppercase text-clay">Plan actuel</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-semibold text-night">{planName}</h2>
            {recommendations ? <span className="rounded bg-night px-2 py-1 text-xs font-semibold text-white">{phaseLabel(recommendations.phase)}</span> : null}
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-700">
            {recommendations?.coachMessage ?? selectedPlan?.learningGoal ?? selectedPlan?.beginnerGoal ?? "Le coach relie les coups au plan choisi."}
          </p>
        </div>

        {loading ? <p className="text-sm text-clay">Mise a jour du plan...</p> : null}
        {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

        {recommendations ? (
          <>
            <div className="grid gap-3 rounded-lg border border-line bg-stone-50 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-white px-2 py-1 text-xs font-semibold text-night">{phaseStatusLabel(recommendations.phaseStatus)}</span>
                {typeof progress?.percent === "number" ? <span className="ml-auto text-sm font-semibold text-sage">{progress.percent}%</span> : null}
              </div>
              <div className="h-2 overflow-hidden rounded bg-white">
                <div className="h-full rounded bg-sage" style={{ width: `${progress?.percent ?? 0}%` }} />
              </div>
              <CoachFact title="Position" value={recommendations.lastEvent || "La partie est prete."} />
              <CoachFact title="Lecture du plan" value={recommendations.whatChanged || recommendations.coachMessage} />
              <CoachFact title="Objectif maintenant" value={recommendations.nextObjective || recommendations.currentObjective} />
            </div>

            {moves.length > 0 ? (
              <div className="grid gap-3">
                <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-clay">Prochain coup du plan</h3>
                {moves.map((item, index) => (
                  <RecommendationCard
                    key={`${item.moveUci}-${index}`}
                    item={item}
                    primary={index === 0}
                    highlighted={highlightedMoveUci === item.moveUci}
                    onToggle={onToggleRecommendation}
                  />
                ))}
              </div>
            ) : (
              <div className="rounded border border-line bg-white px-3 py-2 text-sm text-neutral-700">
                Aucun coup de plan clair pour l&apos;instant. Verifie les details techniques ou joue un coup legal simple.
              </div>
            )}

            {recommendations.blockedExpectedMove ? (
              <div className="rounded border border-clay bg-orange-50 px-3 py-2 text-sm text-night">
                Un coup du plan est mis de cote : {recommendations.blockedExpectedMove.reason}
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}

function CoachFact({ title, value }: { title: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase text-clay">{title}</p>
      <p className="mt-1 text-sm leading-6 text-neutral-700">{value}</p>
    </div>
  );
}

function RecommendationCard({
  item,
  primary,
  highlighted,
  onToggle
}: {
  item: PlanRecommendation;
  primary?: boolean;
  highlighted?: boolean;
  onToggle: (item: PlanRecommendation) => void;
}) {
  return (
    <article className={primary ? "rounded-lg border border-sage bg-white p-4 shadow-sm" : "rounded-lg border border-line bg-white p-4"}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-night px-2 py-1 text-xs font-semibold text-white">{primary ? "Coup du plan" : "Alternative"}</span>
        <span className="rounded bg-stone-100 px-2 py-1 text-xs font-semibold text-night">{complexityLabel(item.moveComplexity)}</span>
        <span className="text-lg font-semibold text-ink">{item.beginnerLabel}</span>
      </div>
      <p className="mt-3 text-sm leading-6 text-neutral-700">
        {item.pedagogicalExplanation ?? `${item.purpose} ${item.planConnection}`}
      </p>
      {item.warning ? <p className="mt-2 text-sm font-semibold text-clay">{item.warning}</p> : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => onToggle(item)} className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night hover:border-sage">
          {highlighted ? "Masquer la fleche" : "Afficher la fleche"}
        </button>
        <span className="text-sm text-neutral-600">Evaluation : {item.evalLabel}</span>
      </div>
      <details className="mt-3 rounded border border-line bg-stone-50 p-3">
        <summary className="cursor-pointer text-sm font-semibold text-night">Details avances</summary>
        <div className="mt-2 grid gap-1 text-sm text-neutral-700">
          <span>SAN : {item.moveSan}</span>
          <span>UCI : {item.moveUci}</span>
          <span>Source : {sourceLabel(item.source)}</span>
          <span>Rang moteur : {item.engineRank ? `#${item.engineRank}` : "hors liste"}</span>
          {item.candidate ? (
            <>
              <span>Eval brute : {item.candidate.evalCp ?? "mat"}</span>
              <span>PV : {item.candidate.pv.join(" ") || "aucune"}</span>
            </>
          ) : null}
        </div>
      </details>
    </article>
  );
}

function complexityLabel(complexity?: string) {
  return {
    simple: "simple",
    moyen: "moyen",
    complexe: "complexe"
  }[complexity ?? "simple"] ?? "simple";
}

function sourceLabel(source: PlanRecommendation["source"]) {
  return {
    plan: "plan",
    engine: "moteur",
    plan_and_engine: "plan + moteur",
    fallback_principle: "principe"
  }[source];
}

function phaseLabel(phase: string) {
  return {
    opening: "Ouverture",
    transition: "Transition",
    middlegame: "Milieu de partie",
    endgame: "Finale"
  }[phase] ?? phase;
}

function phaseStatusLabel(status: string) {
  return {
    opening_in_progress: "Ouverture en cours",
    opening_success: "Ouverture reussie",
    adapted: "Plan adapte",
    transposed: "Transposition signalee",
    fallback: "Plan de secours"
  }[status] ?? status;
}
