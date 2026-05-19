import { bandStatus, type AccuracySessionSummary } from "@/lib/accuracySession";

type Props = {
  summary: AccuracySessionSummary;
  compact?: boolean;
};

export function AccuracyMeter({ summary, compact = false }: Props) {
  if (summary.count === 0) return null;
  const value = summary.weightedAccuracy;
  const status = bandStatus(value, summary.targetBand);
  const lastSample = summary.samples[summary.samples.length - 1];

  return (
    <div className={`accuracy-meter accuracy-meter--${status} ${compact ? "accuracy-meter--compact" : ""}`}>
      <div className="accuracy-meter__row">
        <span className="accuracy-meter__value">{value.toFixed(1)}%</span>
        <span className="accuracy-meter__target">
          cible {summary.targetBand.min}-{summary.targetBand.max}
        </span>
      </div>
      <div className="accuracy-meter__bar">
        <div className="accuracy-meter__bar-target" style={bandStyle(summary.targetBand.min, summary.targetBand.max)} />
        <div className="accuracy-meter__bar-fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      {!compact && lastSample ? (
        <div className="accuracy-meter__last">
          Dernier coup : {lastSample.accuracy.toFixed(0)}% ({lastSample.quality})
        </div>
      ) : null}
    </div>
  );
}

function bandStyle(min: number, max: number): React.CSSProperties {
  return {
    left: `${min}%`,
    width: `${Math.max(0, max - min)}%`
  };
}
