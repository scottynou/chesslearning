"use client";

import type { PlanRecommendationsResponse, PlanRecommendation, SkillLevel, StrategyPlan } from "@/lib/types";

type PlanFirstPanelProps = {
  selectedPlan?: StrategyPlan | null;
  recommendations?: PlanRecommendationsResponse | null;
  skillLevel: SkillLevel;
  loading?: boolean;
  error?: string | null;
  onSelectRecommendation: (recommendation: PlanRecommendation) => void;
  onReviewLastMove?: () => void;
  canReviewLastMove?: boolean;
  reviewLoading?: boolean;
};

export function PlanFirstPanel({
  selectedPlan,
  recommendations,
  skillLevel,
  loading,
  error,
  onSelectRecommendation,
  onReviewLastMove,
  canReviewLastMove,
  reviewLoading
}: PlanFirstPanelProps) {
  const primary = recommendations?.primaryMove ?? recommendations?.planMoves[0] ?? recommendations?.mergedRecommendations[0] ?? null;
  const alternatives = recommendations?.adaptedAlternatives ?? [];
  const progress = recommendations?.planProgress;

  return (
    <section className="panel">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase text-clay">Coach de plan</p>
          <h2 className="text-2xl font-semibold text-night">{recommendations?.selectedPlan?.nameFr ?? selectedPlan?.nameFr ?? "Plan général"}</h2>
          <p className="mt-1 text-sm leading-6 text-neutral-700">
            {recommendations?.coachMessage ?? selectedPlan?.learningGoal ?? selectedPlan?.beginnerGoal ?? "Choisis un plan pour guider la partie."}
          </p>
        </div>
        <span className="rounded bg-night px-3 py-2 text-xs font-semibold text-white">{skillLabel(skillLevel)}</span>
      </div>

      {loading ? <p className="text-sm text-clay">Mise à jour du plan...</p> : null}
      {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {recommendations ? (
        <div className="grid gap-4">
          <div className="rounded border border-line bg-stone-50 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded bg-white px-2 py-1 text-xs font-semibold text-night">{phaseLabel(recommendations.phase)}</span>
              <span className="rounded bg-white px-2 py-1 text-xs font-semibold text-night">{phaseStatusLabel(recommendations.phaseStatus)}</span>
              {typeof progress?.percent === "number" ? (
                <span className="ml-auto text-sm font-semibold text-sage">{progress.percent}%</span>
              ) : null}
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded bg-white">
              <div className="h-full rounded bg-sage" style={{ width: `${progress?.percent ?? 0}%` }} />
            </div>
            <p className="mt-3 text-sm font-semibold text-night">Objectif actuel</p>
            <p className="mt-1 text-sm leading-6 text-neutral-700">{recommendations.currentObjective}</p>
          </div>

          {primary ? (
            <div className="grid gap-2">
              <h3 className="text-sm font-semibold text-night">Coup recommandé</h3>
              <RecommendationCard item={primary} primary onSelect={onSelectRecommendation} />
            </div>
          ) : null}

          {alternatives.length > 0 ? (
            <div className="grid gap-2">
              <h3 className="text-sm font-semibold text-night">Alternatives adaptées</h3>
              {alternatives.map((item) => (
                <RecommendationCard key={item.moveUci} item={item} onSelect={onSelectRecommendation} />
              ))}
            </div>
          ) : null}

          {recommendations.blockedExpectedMove ? (
            <div className="rounded border border-clay bg-orange-50 px-3 py-2 text-sm text-night">
              Le coup attendu du plan est retenu : {recommendations.blockedExpectedMove.reason}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onReviewLastMove}
              disabled={!canReviewLastMove || reviewLoading}
              className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night disabled:cursor-not-allowed disabled:opacity-50"
            >
              {reviewLoading ? "Analyse..." : "Comprendre le dernier coup"}
            </button>
          </div>

          <details className="rounded border border-line bg-white p-3">
            <summary className="cursor-pointer text-sm font-semibold text-night">Critères et détails techniques</summary>
            <div className="mt-3 grid gap-3 text-sm text-neutral-700">
              {progress?.criteria ? (
                <ul className="grid gap-1">
                  {progress.criteria.map((criterion) => (
                    <li key={criterion.label}>{criterion.ok ? "OK" : "À faire"} - {criterion.label}</li>
                  ))}
                </ul>
              ) : null}
              <div className="grid gap-1">
                {(recommendations.technicalEngineMoves ?? []).slice(0, 5).map((move) => (
                  <span key={move.moveUci}>
                    #{move.stockfishRank} {move.moveSan} / {move.moveUci} / eval {move.evalCp ?? "mat"}
                  </span>
                ))}
              </div>
            </div>
          </details>
        </div>
      ) : null}
    </section>
  );
}

function RecommendationCard({ item, primary, onSelect }: { item: PlanRecommendation; primary?: boolean; onSelect: (item: PlanRecommendation) => void }) {
  return (
    <article className={primary ? "rounded border border-sage bg-white p-4 shadow-sm" : "rounded border border-line bg-white p-3"}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-night px-2 py-1 text-xs font-semibold text-white">{primary ? "Plan" : "Alt"}</span>
        <span className="text-base font-semibold text-ink">{item.beginnerLabel}</span>
        <span className="ml-auto text-sm font-semibold text-sage">{item.finalCoachScore}/100</span>
      </div>
      <p className="mt-2 text-sm leading-6 text-neutral-700">But : {item.purpose}</p>
      <p className="mt-1 text-sm leading-6 text-neutral-700">Lien au plan : {item.planConnection}</p>
      {item.warning ? <p className="mt-2 text-sm font-semibold text-clay">{item.warning}</p> : null}
      <button type="button" onClick={() => onSelect(item)} className="mt-3 rounded bg-clay px-3 py-2 text-sm font-semibold text-white">
        Comprendre ce coup
      </button>
    </article>
  );
}

function skillLabel(level: SkillLevel) {
  return {
    beginner: "Débutant",
    intermediate: "Intermédiaire",
    pro: "Pro"
  }[level];
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
    opening_success: "Ouverture réussie",
    adapted: "Plan adapté",
    transposed: "Transposition signalée",
    fallback: "Plan de secours"
  }[status] ?? status;
}
