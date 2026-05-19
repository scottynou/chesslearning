import { bandStatus, type AccuracySample, type AccuracySessionSummary } from "@/lib/accuracySession";

const QUALITY_LABELS: Record<AccuracySample["quality"], string> = {
  excellent: "Excellent",
  good: "Bon",
  playable: "Jouable",
  inaccurate: "Imprécis",
  mistake: "Erreur",
  blunder: "Gaffe"
};

const QUALITY_ORDER: AccuracySample["quality"][] = [
  "excellent",
  "good",
  "playable",
  "inaccurate",
  "mistake",
  "blunder"
];

type Props = {
  summary: AccuracySessionSummary;
  resultText?: string | null;
  onClose?: () => void;
};

export function PostGameReview({ summary, resultText, onClose }: Props) {
  if (summary.count === 0) {
    return (
      <div className="post-game-review">
        <h2>Bilan de partie</h2>
        <p>Aucun coup analysé pour cette partie.</p>
        {onClose ? (
          <button type="button" onClick={onClose} className="post-game-review__close">
            Fermer
          </button>
        ) : null}
      </div>
    );
  }

  const status = bandStatus(summary.weightedAccuracy, summary.targetBand);
  const worst = [...summary.samples]
    .sort((a, b) => a.accuracy - b.accuracy)
    .slice(0, 3);

  return (
    <div className={`post-game-review post-game-review--${status}`}>
      <header className="post-game-review__header">
        <h2>Bilan de partie</h2>
        {resultText ? <p className="post-game-review__result">{resultText}</p> : null}
        {onClose ? (
          <button type="button" onClick={onClose} className="post-game-review__close" aria-label="Fermer">
            ✕
          </button>
        ) : null}
      </header>

      <section className="post-game-review__metrics">
        <Metric
          label="Accuracy globale"
          value={`${summary.weightedAccuracy.toFixed(1)}%`}
          helper={`cible ${summary.targetBand.min}-${summary.targetBand.max}% (profil ${summary.targetBand.profile})`}
        />
        <Metric
          label="Accuracy moyenne"
          value={`${summary.averageAccuracy.toFixed(1)}%`}
          helper="moyenne simple par coup"
        />
        <Metric
          label="ACPL"
          value={summary.acpl.toFixed(1)}
          helper="perte de centipions moyenne"
        />
        <Metric label="Coups analysés" value={String(summary.count)} />
      </section>

      <section className="post-game-review__breakdown">
        {QUALITY_ORDER.map((quality) => (
          <div key={quality} className={`post-game-review__chip post-game-review__chip--${quality}`}>
            <span className="post-game-review__chip-value">{summary.counts[quality]}</span>
            <span className="post-game-review__chip-label">{QUALITY_LABELS[quality]}</span>
          </div>
        ))}
      </section>

      {worst.length > 0 ? (
        <section className="post-game-review__worst">
          <h3>Coups à revoir</h3>
          <ol>
            {worst.map((sample) => (
              <li key={sample.ply}>
                <span>Coup {Math.floor(sample.ply / 2) + 1}{sample.ply % 2 === 0 ? "" : "..."}</span>
                <span className="post-game-review__worst-move">{sample.san ?? sample.uci}</span>
                <span className="post-game-review__worst-acc">{sample.accuracy.toFixed(0)}%</span>
                <span className="post-game-review__worst-quality">{QUALITY_LABELS[sample.quality]}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}

function Metric({ label, value, helper }: { label: string; value: string; helper?: string }) {
  return (
    <div className="post-game-review__metric">
      <span className="post-game-review__metric-label">{label}</span>
      <span className="post-game-review__metric-value">{value}</span>
      {helper ? <span className="post-game-review__metric-helper">{helper}</span> : null}
    </div>
  );
}
