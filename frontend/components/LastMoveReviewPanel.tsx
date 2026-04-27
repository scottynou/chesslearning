"use client";

import type { ReviewMoveResponse } from "@/lib/types";

type LastMoveReviewPanelProps = {
  review?: ReviewMoveResponse | null;
  loading?: boolean;
  error?: string | null;
};

export function LastMoveReviewPanel({ review, loading, error }: LastMoveReviewPanelProps) {
  return (
    <section className="panel">
      <h2 className="panel-title">Analyse du dernier coup</h2>
      {loading ? <p className="text-sm text-clay">Analyse du coup joué...</p> : null}
      {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {!loading && !error && !review ? (
        <p className="text-sm text-neutral-500">Joue un coup pour voir son idée et sa qualité.</p>
      ) : null}
      {review ? (
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold text-night">{review.moveLabel}</span>
            <span className="rounded bg-sage px-2 py-1 text-xs font-semibold text-white">{review.qualityLabel}</span>
          </div>
          <p className="text-sm text-neutral-700">Évaluation : {review.playedMoveEvalLabel}</p>
          {review.bestMoveWasDifferent ? (
            <p className="text-sm text-neutral-700">Meilleur coup recommandé : {review.bestMoveLabel}</p>
          ) : null}
          {review.connectionToPlan ? <ReviewItem title="Lien avec le plan" body={review.connectionToPlan} /> : null}
          <ReviewItem title="Idée probable" body={review.explanation.probableIdea} />
          <ReviewItem title="Ce que ça attaque ou défend" body={review.explanation.whatItDoes} />
          {review.whatItAttacks?.length ? <ReviewItem title="Cases attaquées" body={review.whatItAttacks.join(", ")} /> : null}
          <ReviewItem title="Ce que ça permet ensuite" body={review.explanation.whatItAllows} />
          {review.whatItAllowsNext?.length ? <ReviewItem title="Prochaines étapes" body={review.whatItAllowsNext.join(" ")} /> : null}
          <ReviewItem title="À surveiller" body={review.explanation.whatToWatch} />
          <ReviewItem title="Différence avec le meilleur coup" body={review.explanation.comparisonWithBest} />
        </div>
      ) : null}
    </section>
  );
}

function ReviewItem({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded border border-line bg-stone-50 px-3 py-2">
      <h3 className="text-sm font-semibold text-night">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-neutral-700">{body}</p>
    </div>
  );
}
