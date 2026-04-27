"use client";

import clsx from "clsx";
import { notationFromCandidate } from "@/lib/beginnerNotation";
import { evaluationLabel, technicalEvaluation } from "@/lib/evaluationLabel";
import type { CandidateMove } from "@/lib/types";

type CandidateMoveListProps = {
  fen: string;
  candidates: CandidateMove[];
  selectedMove?: CandidateMove | null;
  loading: boolean;
  error?: string | null;
  onSelect: (candidate: CandidateMove) => void;
};

export function CandidateMoveList({ fen, candidates, selectedMove, loading, error, onSelect }: CandidateMoveListProps) {
  return (
    <section className="panel">
      <div className="flex items-center justify-between gap-3">
        <h2 className="panel-title">Coups candidats</h2>
        {loading ? <span className="text-xs text-clay">Analyse...</span> : null}
      </div>

      {error ? (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {!loading && !error && candidates.length === 0 ? (
        <p className="text-sm text-neutral-500">Aucun coup candidat pour le moment.</p>
      ) : null}

      <div className="coach-scroll grid max-h-[28rem] gap-2 overflow-auto">
        {candidates.map((candidate) => {
          const notation = notationFromCandidate(fen, candidate);
          return (
            <article
              key={`${candidate.rank}-${candidate.moveUci}`}
              className={clsx(
                "grid gap-3 rounded border px-3 py-3 text-left transition",
                selectedMove?.moveUci === candidate.moveUci
                  ? "border-clay bg-orange-50"
                  : "border-line bg-white hover:border-sage hover:bg-stone-50"
              )}
            >
              <button type="button" onClick={() => onSelect(candidate)} className="grid gap-2 text-left">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-night px-2 py-1 text-xs font-semibold text-white">#{candidate.rank}</span>
                  <span className="text-lg font-semibold text-ink">{notation.beginnerLabel}</span>
                  <span className="ml-auto text-sm font-semibold text-sage">{candidate.coachScore}/100</span>
                </div>
                <p className="text-sm text-neutral-700">Idée : {candidate.summary}</p>
                <div className="grid grid-cols-1 gap-2 text-sm text-neutral-700 sm:grid-cols-3">
                  <span>Évaluation : {evaluationLabel(candidate.evalCp, candidate.mateIn)}</span>
                  <span>Risque : {labelRisk(candidate.risk)}</span>
                  <span>Difficulté : {labelDifficulty(candidate.difficulty)}</span>
                </div>
                <span className="w-fit rounded bg-clay px-3 py-2 text-sm font-semibold text-white">Comprendre ce coup</span>
              </button>

              <details className="rounded border border-line bg-stone-50 px-3 py-2 text-xs text-neutral-600">
                <summary className="cursor-pointer font-semibold text-night">Détails techniques</summary>
                <div className="mt-2 grid gap-1">
                  <span>SAN : {candidate.moveSan}</span>
                  <span>UCI : {candidate.moveUci}</span>
                  <span>Stockfish rank : #{candidate.stockfishRank}</span>
                  <span>Eval : {technicalEvaluation(candidate.evalCp, candidate.mateIn)}</span>
                  <span>PV : {candidate.pv.join(" ")}</span>
                </div>
              </details>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function labelRisk(risk: CandidateMove["risk"]) {
  return risk === "low" ? "bas" : risk === "medium" ? "moyen" : "haut";
}

function labelDifficulty(difficulty: CandidateMove["difficulty"]) {
  return difficulty === "easy" ? "facile" : difficulty === "medium" ? "moyen" : "difficile";
}
