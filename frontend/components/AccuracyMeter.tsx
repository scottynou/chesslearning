import { bandStatus, type AccuracySessionSummary } from "@/lib/accuracySession";
import { useI18n } from "@/lib/i18n";

type Props = {
  summary: AccuracySessionSummary;
  compact?: boolean;
};

export function AccuracyMeter({ summary, compact = false }: Props) {
  const { t } = useI18n();
  if (summary.count === 0) return null;
  const value = summary.weightedAccuracy;
  // Si les samples sont invalides ou incomplets, on n'affiche pas le meter.
  if (value < 5) return null;

  const status = bandStatus(value, summary.targetBand);
  const lastSample = summary.samples[summary.samples.length - 1];

  const cursorLeft = Math.max(0, Math.min(100, value));
  const targetLeft = Math.max(0, Math.min(100, summary.targetBand.min));
  const targetWidth = Math.max(0, Math.min(100 - targetLeft, summary.targetBand.max - summary.targetBand.min));

  return (
    <div className={`accuracy-meter accuracy-meter--${status} ${compact ? "accuracy-meter--compact" : ""}`}>
      <div className="accuracy-meter__head">
        <span className="accuracy-meter__value">{value.toFixed(0)}%</span>
        <span className="accuracy-meter__divider" aria-hidden="true">|</span>
        <span className="accuracy-meter__target">
          {t("accuracy.target")} {summary.targetBand.min}–{summary.targetBand.max}%
        </span>
      </div>
      <div className="accuracy-meter__track" aria-hidden="true">
        <div
          className="accuracy-meter__zone"
          style={{ left: `${targetLeft}%`, width: `${targetWidth}%` }}
        />
        <div
          className="accuracy-meter__cursor"
          style={{ left: `${cursorLeft}%` }}
        />
      </div>
      {!compact && lastSample ? (
        <div className="accuracy-meter__last">
          {t("accuracy.lastMove")} : {Math.round(lastSample.accuracy)}% · {t(`quality.${lastSample.quality}`)}
        </div>
      ) : null}
    </div>
  );
}
