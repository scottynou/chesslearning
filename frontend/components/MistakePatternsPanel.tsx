"use client";

import { useEffect, useState } from "react";

import { buildMistakeReport, type MistakeReport } from "@/lib/mistakeTracker";

type Props = {
  onClose?: () => void;
};

const CATEGORY_LABEL: Record<string, string> = {
  blunder: "Gaffes",
  mistake: "Erreurs",
  inaccurate: "Imprécisions"
};

const PHASE_LABEL: Record<string, string> = {
  opening: "Ouverture",
  middlegame: "Milieu de jeu",
  endgame: "Finale"
};

export function MistakePatternsPanel({ onClose }: Props) {
  const [report, setReport] = useState<MistakeReport | null>(null);

  useEffect(() => {
    setReport(buildMistakeReport());
  }, []);

  if (!report) {
    return (
      <div className="saved-games-panel">
        <p>Chargement…</p>
      </div>
    );
  }

  return (
    <div className="saved-games-panel">
      <header className="saved-games-header">
        <h3>Mes patterns d&apos;erreur</h3>
        {onClose ? (
          <button type="button" className="saved-games-close" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        ) : null}
      </header>
      <p className="saved-games-empty">{report.suggestion}</p>
      {report.patterns.length === 0 ? null : (
        <ul className="saved-games-list">
          {report.patterns.slice(0, 8).map((pattern) => (
            <li key={`${pattern.category}-${pattern.phase}`} className="saved-games-item">
              <div className="saved-games-item-main" style={{ cursor: "default" }}>
                <span className="saved-games-item-date">
                  {CATEGORY_LABEL[pattern.category]} · {PHASE_LABEL[pattern.phase]}
                </span>
                <span className="saved-games-item-accuracy">{pattern.count}×</span>
                <span className="saved-games-item-meta">
                  Perte moyenne : {Math.round(pattern.averageLoss)} cp
                  {pattern.examples.length > 0 ? ` — ex : ${pattern.examples.map((e) => e.san ?? "?").join(", ")}` : ""}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
