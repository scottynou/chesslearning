"use client";

import type { PlanRecommendation, PlanRecommendationsResponse, StrategyPlan } from "@/lib/types";

type PlanFirstPanelProps = {
  selectedPlan?: StrategyPlan | null;
  recommendations?: PlanRecommendationsResponse | null;
  loading?: boolean;
  error?: string | null;
};

export function PlanFirstPanel({ selectedPlan, recommendations, loading, error }: PlanFirstPanelProps) {
  const phaseDisplay = recommendations?.phaseDisplay;
  const progress = recommendations?.planProgress;
  const isOpening = phaseDisplay?.key === "opening";
  const planName = recommendations?.selectedPlan?.nameFr ?? selectedPlan?.nameFr ?? "Plan";
  const moves = recommendations?.mergedRecommendations ?? [];
  const expectedOpponentMove = recommendations?.expectedOpponentMove ?? null;
  const hasStaleRecommendations = Boolean(loading && recommendations);

  return (
    <section className="live-coach-panel is-fast-coach">
      <div className="live-coach-header">
        <div>
          <p className="live-coach-kicker">Coups</p>
          <div className="live-coach-title-row">
            <h2>{planName}</h2>
            {phaseDisplay ? <span>{phaseDisplay.label}</span> : null}
          </div>
        </div>

        {isOpening && typeof progress?.percent === "number" ? (
          <div className="live-progress-orb" aria-label={`Progression du plan ${progress.percent}%`}>
            <strong>{progress.percent}%</strong>
            <span>plan</span>
          </div>
        ) : null}
      </div>

      {isOpening && typeof progress?.percent === "number" ? (
        <div className="live-status-card">
          <div className="live-status-top">
            <span>Ouverture</span>
            <span>{progress.percent}%</span>
          </div>
          <div className="live-progress-track"><div style={{ width: `${progress.percent}%` }} /></div>
        </div>
      ) : null}

      {loading ? <div className="coach-updating-banner" role="status">{hasStaleRecommendations ? "Recalcul..." : "Calcul..."}</div> : null}
      {error ? <div className="live-error">{error}</div> : null}

      {recommendations ? (
        moves.length > 0 ? (
          <div className="live-move-section">
            <h3>{phaseDisplay?.recommendationStyle === "ranked" ? "Coups proposes" : "Coup recommande"}</h3>
            {moves.map((item, index) => (
              <RecommendationCard key={`${item.moveUci}-${index}`} item={item} primary={index === 0} />
            ))}
          </div>
        ) : expectedOpponentMove ? (
          <div className="live-move-section is-opponent-move">
            <h3>Coup adverse attendu</h3>
            <RecommendationCard
              item={{
                ...expectedOpponentMove,
                displayRole: expectedOpponentMove.displayRole ?? "Adversaire",
                arrowColor: expectedOpponentMove.arrowColor ?? "rgba(239,118,118,0.78)"
              }}
              primary
            />
          </div>
        ) : recommendations.turnContext?.gameOver ? (
          <div className="live-empty">Partie terminee.</div>
        ) : (
          <div className="live-empty">Aucun coup legal disponible.</div>
        )
      ) : null}
    </section>
  );
}

function RecommendationCard({ item, primary }: { item: PlanRecommendation; primary?: boolean }) {
  return (
    <article className={primary ? "live-move-card is-primary" : "live-move-card"}>
      <div className="live-move-head">
        <div className="live-move-badges">
          <span className="live-priority-badge">
            <i style={{ backgroundColor: item.arrowColor ?? "rgba(224,185,118,0.78)" }} aria-hidden="true" />
            {item.displayRole ?? (primary ? "Meilleur" : "Option")}
          </span>
        </div>
        <strong>{item.beginnerLabel}</strong>
      </div>
    </article>
  );
}
