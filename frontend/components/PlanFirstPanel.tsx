"use client";

import type {
  LivePlanInsightResponse,
  PlanEvent,
  PlanRecommendation,
  PlanRecommendationsResponse,
  StrategyPlan
} from "@/lib/types";

type PlanFirstPanelProps = {
  selectedPlan?: StrategyPlan | null;
  recommendations?: PlanRecommendationsResponse | null;
  liveInsight?: LivePlanInsightResponse | null;
  liveInsightLoading?: boolean;
  liveInsightError?: string | null;
  events?: PlanEvent[];
  loading?: boolean;
  error?: string | null;
};

export function PlanFirstPanel({
  selectedPlan,
  recommendations,
  liveInsight,
  liveInsightLoading,
  liveInsightError,
  events = [],
  loading,
  error
}: PlanFirstPanelProps) {
  const primary = recommendations?.primaryMove ?? null;
  const expectedOpponentMove = recommendations?.expectedOpponentMove ?? null;
  const progress = recommendations?.planProgress;
  const openingBrief = recommendations?.openingBrief;
  const phaseDisplay = recommendations?.phaseDisplay;
  const isOpening = phaseDisplay?.key === "opening";
  const planName = recommendations?.selectedPlan?.nameFr ?? selectedPlan?.nameFr ?? "Plan general";
  const moves = recommendations?.mergedRecommendations ?? [];
  const expectedOpponentCard = expectedOpponentMove
    ? {
        ...expectedOpponentMove,
        displayRole: expectedOpponentMove.displayRole ?? "Coup adverse attendu",
        arrowColor: expectedOpponentMove.arrowColor ?? "rgba(239,118,118,0.78)"
      }
    : null;
  const hasStaleRecommendations = Boolean(loading && recommendations);
  const strategicPlan = recommendations?.strategicPlan;
  const liveHeadline = liveInsight?.headline ?? strategicPlan?.title ?? "Plan actuel";
  const liveCurrentPlan = liveInsight?.currentPlan ?? strategicPlan?.goal ?? "Le coach attend la position actuelle.";
  const liveWhyChanged = liveInsight?.whyChanged ?? strategicPlan?.reason ?? recommendations?.phaseReason ?? "";
  const liveNextGoal = liveInsight?.nextGoal ?? strategicPlan?.nextObjective ?? recommendations?.currentObjective ?? "";

  return (
    <section className="live-coach-panel">
      <div className="live-coach-header">
        <div>
          <p className="live-coach-kicker">Coach en direct</p>
          <div className="live-coach-title-row">
            <h2>{planName}</h2>
            {phaseDisplay ? <span>{phaseDisplay.label}</span> : recommendations ? <span>{phaseLabel(recommendations.phase)}</span> : null}
          </div>
          <p className="live-coach-message">
            {compactText(
              isOpening
                ? openingBrief?.summary ?? selectedPlan?.learningGoal ?? selectedPlan?.beginnerGoal ?? "Le coach construit le plan choisi."
                : recommendations?.phaseReason ?? phaseDisplay?.subtitle ?? "Le coach adapte le plan a la position.",
              190
            )}
          </p>
        </div>
        {isOpening && typeof progress?.percent === "number" ? (
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
          <div className="live-plan-card">
            <div className="live-plan-card-head">
              <span>Plan actuel</span>
              {liveInsightLoading ? <i>Mise a jour...</i> : null}
            </div>
            <h3>{compactText(liveHeadline, 90)}</h3>
            <p>{compactText(liveCurrentPlan, 230)}</p>
            <div className="live-plan-facts">
              {liveWhyChanged ? <CoachFact title="Pourquoi" value={compactText(liveWhyChanged, 170)} /> : null}
              {liveNextGoal ? <CoachFact title="Prochain objectif" value={compactText(liveNextGoal, 170)} /> : null}
            </div>
            {liveInsightError ? <p className="live-insight-state">{liveInsightError}</p> : null}
          </div>

          <div className="live-status-card">
            <div className="live-status-top">
              <span>{phaseDisplay?.label ?? phaseStatusLabel(recommendations.phaseStatus)}</span>
              <span>{isOpening && typeof progress?.percent === "number" ? `${progress.percent}%` : openingStateLabel(recommendations.openingState)}</span>
            </div>
            {isOpening ? <div className="live-progress-track"><div style={{ width: `${progress?.percent ?? 0}%` }} /></div> : null}
            <div className="live-fact-grid">
              {isOpening ? (
                <>
                  <CoachFact title="Fin de l'ouverture" value={compactText(openingBrief?.completion ?? recommendations.currentObjective, 170)} />
                  <CoachFact title="Impact" value={compactText(progress?.impact ?? recommendations.phaseReason ?? "Le coach verifie si le plan avance.", 170)} />
                </>
              ) : (
                <>
                  <CoachFact title="Phase" value={compactText(recommendations.phaseReason, 170)} />
                  <CoachFact title="Objectif" value={compactText(recommendations.currentObjective, 170)} />
                </>
              )}
            </div>
          </div>

          {events.length > 0 ? <EventFeed events={events} /> : null}

          {moves.length > 0 ? (
            <div className="live-move-section">
              <h3>{phaseDisplay?.recommendationStyle === "ranked" ? "Choix strategiques" : "Coup recommande"}</h3>
              {moves.map((item, index) => (
                <RecommendationCard key={`${item.moveUci}-${index}`} item={item} primary={index === 0} />
              ))}
            </div>
          ) : expectedOpponentCard ? (
            <div className="live-move-section is-opponent-move">
              <h3>Coup adverse attendu</h3>
              <RecommendationCard item={expectedOpponentCard} primary />
            </div>
          ) : recommendations.turnContext?.gameOver ? (
            <div className="live-empty">Partie terminee. Aucun coup legal a conseiller.</div>
          ) : (
            <div className="live-empty">Le plateau reste jouable. Le coach attend un coup legal clair.</div>
          )}

          {recommendations.blockedExpectedMove ? <div className="live-warning">Coup de ligne mis de cote : {recommendations.blockedExpectedMove.reason}</div> : null}
        </>
      ) : loading ? (
        <CoachLoadingSkeleton />
      ) : null}
    </section>
  );
}

function EventFeed({ events }: { events: PlanEvent[] }) {
  return (
    <div className="live-event-feed" aria-label="Evenements du plan">
      {events.slice(0, 4).map((event) => (
        <article key={event.id} className={`live-event is-${event.severity}`}>
          <span>{event.title}</span>
          <p>{event.message}</p>
        </article>
      ))}
    </div>
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
        <p>{stale ? "Ancien conseil affiche pendant le recalcul." : "Analyse de la position actuelle."}</p>
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

function RecommendationCard({ item, primary }: { item: PlanRecommendation; primary?: boolean }) {
  return (
    <article className={primary ? "live-move-card is-primary" : "live-move-card"}>
      <div className="live-move-head">
        <div className="live-move-badges">
          <span className="live-priority-badge">
            <i style={{ backgroundColor: item.arrowColor ?? "rgba(224,185,118,0.78)" }} aria-hidden="true" />
            {item.displayRole ?? (primary ? "Coup du plan" : "Alternative")}
          </span>
          <span>{complexityLabel(item.moveComplexity)}</span>
        </div>
        <strong>{item.beginnerLabel}</strong>
      </div>
      {item.warning ? <p className="live-move-warning">{item.warning}</p> : null}
      <details className="live-technical-details">
        <summary>Details avances</summary>
        <div>
          <span>SAN : {item.moveSan}</span>
          <span>UCI : {item.moveUci}</span>
          <span>Source : {sourceLabel(item.source)}</span>
          <span>Evaluation : {item.evalLabel}</span>
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

function compactText(value: string, limit = 220) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).replace(/[\s,.;:!?]+\S*$/, "")}...`;
}

function complexityLabel(complexity?: string) {
  return { simple: "simple", moyen: "moyen", complexe: "complexe" }[complexity ?? "simple"] ?? "simple";
}

function sourceLabel(source: PlanRecommendation["source"]) {
  return { plan: "plan", engine: "moteur", plan_and_engine: "plan + moteur", fallback_principle: "principe" }[source];
}

function phaseLabel(phase: string) {
  return { opening: "Ouverture", transition: "Milieu de partie", middlegame: "Milieu de partie", endgame: "Finale" }[phase] ?? phase;
}

function phaseStatusLabel(status: string) {
  return { opening_in_progress: "Ouverture en cours", opening_success: "Ouverture reussie", adapted: "Plan adapte", transposed: "Transposition signalee", fallback: "Plan de secours" }[status] ?? status;
}

function openingStateLabel(state: string) {
  return { on_track: "sur le plan", recoverable: "adaptable", completed: "terminee", abandoned: "abandonnee" }[state] ?? state;
}
