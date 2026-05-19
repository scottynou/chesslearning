import { bandStatus, type AccuracySessionSummary } from "@/lib/accuracySession";

type Props = {
  summary: AccuracySessionSummary;
  compact?: boolean;
};

export function AccuracyMeter({ summary, compact = false }: Props) {
  if (summary.count === 0) return null;
  const value = summary.weightedAccuracy;
  // Si les samples sont invalides (toutes accuracies a 0 -> harmonic = 1),
  // on n'affiche pas le meter.
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
          cible {summary.targetBand.min}–{summary.targetBand.max}%
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
          Dernier coup : {Math.round(lastSample.accuracy)}% · {qualityLabel(lastSample.quality)}
        </div>
      ) : null}
    </div>
  );
}

function qualityLabel(quality: string): string {
  const map: Record<string, string> = {
    excellent: "Excellent",
    good: "Bon",
    playable: "Jouable",
    inaccurate: "Imprécis",
    mistake: "Erreur",
    blunder: "Gaffe"
  };
  return map[quality] ?? quality;
}
