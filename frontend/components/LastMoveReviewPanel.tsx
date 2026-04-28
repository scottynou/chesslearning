"use client";

import type { ReviewMoveResponse } from "@/lib/types";

type LastMoveReviewPanelProps = {
  review?: ReviewMoveResponse | null;
  loading?: boolean;
  error?: string | null;
};

export function LastMoveReviewPanel({ review, loading, error }: LastMoveReviewPanelProps) {
  return (
    <section className="panel review-panel">
      <div className="review-panel-head">
        <p className="panel-eyebrow">Dernier coup</p>
        <h2 className="panel-title">Analyse compacte</h2>
      </div>

      {loading ? <p className="review-loading">Analyse en cours...</p> : null}
      {error ? <div className="error-alert">{error}</div> : null}
      {!loading && !error && !review ? <p className="review-empty">Joue un coup. Le coach resume son idee, sa qualite et le risque principal.</p> : null}

      {review ? (
        <div className="review-content">
          <div className="review-score-card">
            <div>
              <span>Coup joue</span>
              <strong>{review.moveLabel}</strong>
            </div>
            <div>
              <span>Qualite</span>
              <strong>{review.qualityLabel}</strong>
            </div>
            <div>
              <span>Evaluation</span>
              <strong>{review.playedMoveEvalLabel}</strong>
            </div>
          </div>

          {review.bestMoveWasDifferent ? (
            <div className="review-best-move">
              <span>Meilleur repere</span>
              <strong>{review.bestMoveLabel}</strong>
            </div>
          ) : null}

          {review.connectionToPlan ? <ReviewItem title="Lien avec le plan" body={compactText(review.connectionToPlan, 260)} /> : null}
          <ReviewItem title="Idee probable" body={compactText(review.explanation.probableIdea, 260)} />
          <ReviewItem title="Risque principal" body={compactText(review.explanation.whatToWatch, 260)} />

          <details className="review-details">
            <summary>Analyse complete</summary>
            <ReviewItem title="Ce que ça attaque ou défend" body={review.explanation.whatItDoes} />
            {review.whatItAttacks?.length ? <ReviewItem title="Cases attaquées" body={review.whatItAttacks.join(", ")} /> : null}
            <ReviewItem title="Ce que ça permet ensuite" body={review.explanation.whatItAllows} />
            {review.whatItAllowsNext?.length ? <ReviewItem title="Prochaines étapes" body={review.whatItAllowsNext.join(" ")} /> : null}
            <ReviewItem title="Différence avec le meilleur coup" body={review.explanation.comparisonWithBest} />
          </details>
        </div>
      ) : null}
    </section>
  );
}

function ReviewItem({ title, body }: { title: string; body: string }) {
  return (
    <div className="review-item">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

function compactText(value: string, limit: number) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).replace(/[\s,.;:!?]+\S*$/, "")}…`;
}
