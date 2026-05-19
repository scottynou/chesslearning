import { bandStatus, type AccuracySample, type AccuracySessionSummary } from "@/lib/accuracySession";
import { useI18n } from "@/lib/i18n";

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
  const { t } = useI18n();

  if (summary.count === 0) {
    return (
      <div className="post-game-review">
        <h2>{t("review.title")}</h2>
        <p>—</p>
        {onClose ? (
          <button type="button" onClick={onClose} className="post-game-review__close">
            {t("review.close")}
          </button>
        ) : null}
      </div>
    );
  }

  const status = bandStatus(summary.weightedAccuracy, summary.targetBand);
  const worst = [...summary.samples].sort((a, b) => a.accuracy - b.accuracy).slice(0, 3);

  return (
    <div className={`post-game-review post-game-review--${status}`}>
      <header className="post-game-review__header">
        <h2>{t("review.title")}</h2>
        {resultText ? <p className="post-game-review__result">{resultText}</p> : null}
        {onClose ? (
          <button type="button" onClick={onClose} className="post-game-review__close" aria-label={t("review.close")}>
            ✕
          </button>
        ) : null}
      </header>

      <section className="post-game-review__metrics">
        <Metric
          label={t("review.globalAccuracy")}
          value={`${summary.weightedAccuracy.toFixed(1)}%`}
          helper={t("review.targetHelp", {
            min: summary.targetBand.min,
            max: summary.targetBand.max,
            profile: summary.targetBand.profile
          })}
        />
        <Metric
          label={t("review.avgAccuracy")}
          value={`${summary.averageAccuracy.toFixed(1)}%`}
          helper={t("review.avgPerMove")}
        />
        <Metric label={t("review.acpl")} value={summary.acpl.toFixed(1)} helper={t("review.cpLossAvg")} />
        <Metric label={t("review.movesAnalyzed")} value={String(summary.count)} />
      </section>

      <section className="post-game-review__breakdown">
        {QUALITY_ORDER.map((quality) => (
          <div key={quality} className={`post-game-review__chip post-game-review__chip--${quality}`}>
            <span className="post-game-review__chip-value">{summary.counts[quality]}</span>
            <span className="post-game-review__chip-label">{t(`quality.${quality}`)}</span>
          </div>
        ))}
      </section>

      {worst.length > 0 ? (
        <section className="post-game-review__worst">
          <h3>{t("review.movesToReview")}</h3>
          <ol>
            {worst.map((sample) => (
              <li key={sample.ply}>
                <span>
                  {Math.floor(sample.ply / 2) + 1}
                  {sample.ply % 2 === 0 ? "" : "..."}
                </span>
                <span className="post-game-review__worst-move">{sample.san ?? sample.uci}</span>
                <span className="post-game-review__worst-acc">{sample.accuracy.toFixed(0)}%</span>
                <span className="post-game-review__worst-quality">{t(`quality.${sample.quality}`)}</span>
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
