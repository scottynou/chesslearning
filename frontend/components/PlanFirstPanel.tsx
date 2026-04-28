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
  const primary = recommendations?.primaryMove ?? null;
  const expectedOpponentMove = recommendations?.expectedOpponentMove ?? null;
  const alternatives = recommendations?.adaptedAlternatives ?? [];
  const progress = recommendations?.planProgress;
  const phaseDisplay = recommendations?.phaseDisplay;
  const isOpening = phaseDisplay?.key === "opening";
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
            {phaseDisplay ? <span>{phaseDisplay.label}</span> : recommendations ? <span>{phaseLabel(recommendations.phase)}</span> : null}
          </div>
          <p className="live-coach-message">
            {compactText(phaseDisplay?.subtitle ?? recommendations?.coachMessage ?? selectedPlan?.learningGoal ?? selectedPlan?.beginnerGoal ?? "Le coach relie le coup au plan choisi.", 180)}
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
          <div className="live-status-card">
            <div className="live-status-top">
              <span>{phaseDisplay?.label ?? phaseStatusLabel(recommendations.phaseStatus)}</span>
              <span>{isOpening && typeof progress?.percent === "number" ? `${progress.percent}%` : "Objectif"}</span>
            </div>
            {isOpening ? <div className="live-progress-track"><div style={{ width: `${progress?.percent ?? 0}%` }} /></div> : null}
            <div className="live-fact-grid">
              <CoachFact title={isOpening ? "Avancee" : "Plan actuel"} value={compactText(isOpening ? recommendations.whatChanged || recommendations.coachMessage : recommendations.nextObjective || recommendations.currentObjective, 170)} />
              <CoachFact title="Dernier fait" value={compactText(recommendations.lastEvent || "La partie est prete.", 150)} />
              {expectedOpponentMove ? <CoachFact title="Reponse adverse attendue" value={`Ligne du plan : ${expectedOpponentMove.beginnerLabel}.`} /> : null}
              {expectedReplyLabel ? <CoachFact title="Reponse attendue" value={`Ligne du plan : ${expectedReplyLabel}. Sinon, on adapte.`} /> : null}
            </div>
          </div>

          {moves.length > 0 ? (
            <div className="live-move-section">
              <h3>{phaseDisplay?.recommendationStyle === "ranked" ? "Choix strategiques" : "Coup recommande"}</h3>
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
          ) : expectedOpponentMove ? (
            <div className="live-empty">A l&apos;adversaire de jouer. Ligne attendue : {expectedOpponentMove.beginnerLabel}.</div>
          ) : (
            <div className="live-empty">Aucun coup de plan clair. Joue un coup legal simple ou consulte les details.</div>
          )}

          {recommendations.blockedExpectedMove ? <div className="live-warning">Coup de ligne mis de cote : {recommendations.blockedExpectedMove.reason}</div> : null}
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
  const explanation = item.pedagogicalExplanation ?? [item.purpose, item.planConnection].filter(Boolean).join(" ");

  return (
    <article className={primary ? "live-move-card is-primary" : "live-move-card"}>
      <div className="live-move-head">
        <div className="live-move-badges">
          <span>{item.displayRole ?? (primary ? "Coup du plan" : "Alternative")}</span>
          <span>{complexityLabel(item.moveComplexity)}</span>
        </div>
        <strong>{item.beginnerLabel}</strong>
      </div>
      <p className="live-move-explanation">{compactText(explanation, 320)}</p>
      {item.warning ? <p className="live-move-warning">{item.warning}</p> : null}
      <div className="live-move-actions">
        <button type="button" onClick={() => onToggle(item)} className="opening-detail-toggle">
          {highlighted ? "Focus actif" : "Focus plateau"}
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

function compactText(value: string, limit = 220) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).replace(/[\s,.;:!?]+\S*$/, "")}…`;
}

function complexityLabel(complexity?: string) {
  return { simple: "simple", moyen: "moyen", complexe: "complexe" }[complexity ?? "simple"] ?? "simple";
}

function sourceLabel(source: PlanRecommendation["source"]) {
  return { plan: "plan", engine: "moteur", plan_and_engine: "plan + moteur", fallback_principle: "principe" }[source];
}

function phaseLabel(phase: string) {
  return { opening: "Ouverture", transition: "Transition", middlegame: "Milieu de partie", endgame: "Finale" }[phase] ?? phase;
}

function phaseStatusLabel(status: string) {
  return { opening_in_progress: "Ouverture en cours", opening_success: "Ouverture reussie", adapted: "Plan adapte", transposed: "Transposition signalee", fallback: "Plan de secours" }[status] ?? status;
}
