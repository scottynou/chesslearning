"use client";

import type { PlanRecommendation, PlanRecommendationsResponse, StrategyPlan } from "@/lib/types";

type PlanFirstPanelProps = {
  selectedPlan?: StrategyPlan | null;
  recommendations?: PlanRecommendationsResponse | null;
  loading?: boolean;
  error?: string | null;
  highlightedMoveUci?: string | null;
  expectedReplyLabel?: string | null;
  onToggleRecommendation: (recommendation: PlanRecommendation) => void;
};

export function PlanFirstPanel({
  selectedPlan,
  recommendations,
  loading,
  error,
  highlightedMoveUci,
  expectedReplyLabel,
  onToggleRecommendation
}: PlanFirstPanelProps) {
  const primary = recommendations?.primaryMove ?? recommendations?.planMoves[0] ?? recommendations?.mergedRecommendations[0] ?? null;
  const alternatives = recommendations?.adaptedAlternatives ?? [];
  const progress = recommendations?.planProgress;
  const planName = recommendations?.selectedPlan?.nameFr ?? selectedPlan?.nameFr ?? "Plan general";
  const moves = [primary, ...alternatives].filter(Boolean) as PlanRecommendation[];
  const hasStaleRecommendations = Boolean(loading && recommendations);

  return (
    <section className="live-coach-panel">
      <div className="live-coach-header">
        <div>
          <p className="live-coach-kicker">Coach en direct</p>
          <div className="live-coach-title-row">
            <h2>{planName}</h2>
            {recommendations ? <span>{phaseLabel(recommendations.phase)}</span> : null}
          </div>
          <p className="live-coach-message">
            {recommendations?.coachMessage ?? selectedPlan?.learningGoal ?? selectedPlan?.beginnerGoal ?? "Le coach relie les coups au plan choisi."}
          </p>
        </div>
        {typeof progress?.percent === "number" ? (
          <div className="live-progress-orb" aria-label={`Progression du plan ${progress.percent}%`}>
            <strong>{progress.percent}%</strong>
            <span>plan</span>
          </div>
        ) : null}
      </div>

      {loading ? <CoachUpdatingBanner stale={hasStaleRecommendations} /> : null}
      {error ? <div className="live-error">{error}</div> : null}

      {recommendations ? (
        <>
          <div className="live-status-card">
            <div className="live-status-top">
              <span>{phaseStatusLabel(recommendations.phaseStatus)}</span>
              <span>{typeof progress?.percent === "number" ? `${progress.percent}%` : "En cours"}</span>
            </div>
            <div className="live-progress-track">
              <div style={{ width: `${progress?.percent ?? 0}%` }} />
            </div>
            <div className="live-fact-grid">
              <CoachFact title="Ce qui vient de se passer" value={recommendations.lastEvent || "La partie est prete."} />
              <CoachFact title="Ce que cela change" value={recommendations.whatChanged || recommendations.coachMessage} />
              <CoachFact title="Prochain objectif" value={recommendations.nextObjective || recommendations.currentObjective} />
              {expectedReplyLabel ? (
                <CoachFact title="Reponse attendue" value={`Si l'autre camp suit la ligne du plan : ${expectedReplyLabel}. S'il joue autre chose, on garde le plan et on adapte le prochain coup.`} />
              ) : null}
            </div>
          </div>

          {moves.length > 0 ? (
            <div className="live-move-section">
              <h3>Coups pour suivre ou adapter le plan</h3>
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
            <div className="live-empty">
              Aucun coup de plan clair pour l&apos;instant. Verifie les details techniques ou joue un coup legal simple.
            </div>
          )}

          {recommendations.blockedExpectedMove ? (
            <div className="live-warning">
              Un coup du plan est mis de cote : {recommendations.blockedExpectedMove.reason}
            </div>
          ) : null}
        </>
      ) : loading ? (
        <CoachLoadingSkeleton />
      ) : null}
    </section>
  );
}

function CoachFact({ title, value }: { title: string; value: string }) {
  return (
    <div className="live-fact">
      <p>{title}</p>
      <span>{value}</span>
    </div>
  );
}

function CoachUpdatingBanner({ stale }: { stale: boolean }) {
  return (
    <div className="coach-updating-banner" role="status">
      <span className="coach-spinner" aria-hidden="true" />
      <div>
        <strong>Mise a jour du plan...</strong>
        <p>{stale ? "Les conseils affiches datent du coup precedent. Le coach recalcule la position actuelle." : "Le coach analyse la position actuelle."}</p>
      </div>
    </div>
  );
}

function CoachLoadingSkeleton() {
  return (
    <div className="coach-skeleton" aria-hidden="true">
      <span />
      <span />
      <span />
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
    <article className={primary ? "live-move-card is-primary" : "live-move-card"}>
      <div className="live-move-head">
        <div className="live-move-badges">
          <span>{primary ? "Coup du plan" : "Alternative"}</span>
          <span>{complexityLabel(item.moveComplexity)}</span>
        </div>
        <strong>{item.beginnerLabel}</strong>
      </div>
      <p className="live-move-explanation">
        {item.pedagogicalExplanation ?? `${item.purpose} ${item.planConnection}`}
      </p>
      {item.warning ? <p className="live-move-warning">{item.warning}</p> : null}
      <div className="live-move-actions">
        <button type="button" onClick={() => onToggle(item)} className="opening-detail-toggle">
          {highlighted ? "Masquer la fleche" : "Afficher la fleche"}
        </button>
        <span>Evaluation : {item.evalLabel}</span>
      </div>
      <details className="live-technical-details">
        <summary>Details avances</summary>
        <div>
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
