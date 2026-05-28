"use client";

import { useEffect, useMemo, useState } from "react";
import { getCalibrationReport } from "@/lib/api";
import type { CalibrationReportResponse } from "@/lib/types";

type Props = {
  onClose: () => void;
};

const PROFILE_ORDER = ["beginner", "lambda", "strong", "veryStrong"] as const;

export function CalibrationReportPanel({ onClose }: Props) {
  const [report, setReport] = useState<CalibrationReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getCalibrationReport(1600)
      .then((data) => {
        if (!alive) return;
        setReport(data);
        setError(null);
      })
      .catch((err) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Rapport indisponible.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const groupedRows = useMemo(() => {
    if (!report) return [];
    return PROFILE_ORDER.map((profile) => ({
      profile,
      rows: report.rows.filter((row) => row.profile === profile)
    })).filter((group) => group.rows.length > 0);
  }, [report]);

  return (
    <section className="calibration-panel">
      <header className="calibration-header">
        <div>
          <p>Calibration</p>
          <h3>Equilibre humanisation / winrate</h3>
        </div>
        <button type="button" onClick={onClose} className="saved-games-close" aria-label="Fermer">x</button>
      </header>

      {loading ? <div className="calibration-state">Calcul du rapport...</div> : null}
      {error ? <div className="calibration-error">{error}</div> : null}

      {report ? (
        <>
          <div className="calibration-summary">
            <span>Adversaire moyen {report.opponentElo}</span>
            <span>{report.sampleCount} suites types</span>
            <span>Winrate proxy</span>
          </div>

          <div className="calibration-groups">
            {groupedRows.map((group) => {
              const bestStyle = report.bestByProfile[group.profile];
              const title = group.rows[0]?.profileLabel ?? group.profile;
              return (
                <section key={group.profile} className="calibration-group">
                  <div className="calibration-group-head">
                    <h4>{title}</h4>
                    <span>Sweet spot : {styleLabelFor(bestStyle, group.rows)}</span>
                  </div>

                  <div className="calibration-table" role="table" aria-label={`Calibration ${title}`}>
                    <div className="calibration-row calibration-row--head" role="row">
                      <span>Style</span>
                      <span>Winrate</span>
                      <span>Humain</span>
                      <span>Acc.</span>
                      <span>Top engine</span>
                    </div>
                    {group.rows.map((row) => (
                      <div
                        key={`${row.profile}-${row.style}`}
                        className={`calibration-row ${row.style === bestStyle ? "is-best" : ""}`}
                        role="row"
                        title={row.recommendation}
                      >
                        <span>{row.styleLabel}</span>
                        <strong>{row.winRateVsOpponent.toFixed(1)}%</strong>
                        <span>{row.humanizationScore}/100</span>
                        <span>{row.minAccuracy}-{row.maxAccuracy}%</span>
                        <span>{row.topEngineMoveRate.toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>

          <p className="calibration-method">{report.methodology}</p>
        </>
      ) : null}
    </section>
  );
}

function styleLabelFor(style: string | undefined, rows: CalibrationReportResponse["rows"]) {
  return rows.find((row) => row.style === style)?.styleLabel ?? style ?? "-";
}
