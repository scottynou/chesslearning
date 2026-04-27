"use client";

import type { ExplainResponse } from "@/lib/types";

type MoveExplanationPanelProps = {
  explanation?: ExplainResponse | null;
  loading: boolean;
  error?: string | null;
};

export function MoveExplanationPanel({ explanation, loading, error }: MoveExplanationPanelProps) {
  return (
    <section className="panel">
      <h2 className="panel-title">Explication</h2>
      {loading ? <p className="text-sm text-clay">Préparation de l&apos;explication...</p> : null}
      {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {!loading && !error && !explanation ? (
        <p className="text-sm text-neutral-500">Sélectionne un coup candidat pour comprendre le plan.</p>
      ) : null}
      {explanation ? (
        <div className="grid gap-4">
          <div>
            <p className="text-sm font-semibold text-clay">{explanation.moveLabel}</p>
            <h3 className="text-xl font-semibold text-night">{explanation.title}</h3>
            <p className="mt-2 text-sm leading-6 text-neutral-700">{explanation.oneSentence}</p>
          </div>
          <ExplanationItem title="Ce que je dois jouer" body={explanation.sections.whatToDo} />
          <ExplanationItem title="Idée principale" body={explanation.sections.mainIdea} />
          <ExplanationItem title="Pourquoi maintenant" body={explanation.sections.whyNow} />
          <ExplanationItem title="Ce que ça provoque" body={explanation.sections.whatItProvokes} />
          <div className="rounded border border-line bg-stone-50 px-3 py-3">
            <h4 className="text-sm font-semibold text-night">Plan en 3 idées</h4>
            <ol className="mt-2 grid gap-1 text-sm text-neutral-700">
              {explanation.sections.nextPlan.slice(0, 4).map((step, index) => (
                <li key={step}>
                  {index + 1}. {step}
                </li>
              ))}
            </ol>
          </div>
          <ExplanationItem title="Danger" body={explanation.sections.danger} />
          <ExplanationItem title="Erreur fréquente" body={explanation.sections.commonMistake} />
          <ExplanationItem title="Comparaison" body={explanation.sections.betterThan} />

          {explanation.translatedPv.length > 0 ? (
            <details className="rounded border border-line bg-white px-3 py-3 text-sm">
              <summary className="cursor-pointer font-semibold text-night">Plan moteur traduit</summary>
              <div className="mt-3 grid gap-2">
                {explanation.translatedPv.slice(0, 5).map((move) => (
                  <div key={`${move.moveNumber}-${move.beginnerLabel}`} className="rounded bg-stone-50 p-2">
                    <p className="font-semibold">{move.moveNumber}. {move.beginnerLabel}</p>
                    <p className="text-neutral-700">{move.simpleExplanation}</p>
                  </div>
                ))}
              </div>
            </details>
          ) : null}

          <details className="rounded border border-line bg-stone-50 px-3 py-3 text-sm">
            <summary className="cursor-pointer font-semibold text-night">Détails techniques</summary>
            <div className="mt-2 grid gap-1 text-neutral-700">
              <span>SAN : {explanation.technical.san}</span>
              <span>UCI : {explanation.technical.uci}</span>
              <span>Eval : {explanation.technical.evalCp ?? "n/a"} cp</span>
              <span>PV : {explanation.technical.pv.join(" ")}</span>
            </div>
          </details>
        </div>
      ) : null}
    </section>
  );
}

function ExplanationItem({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded border border-line bg-stone-50 px-3 py-3">
      <h4 className="text-sm font-semibold text-night">{title}</h4>
      <p className="mt-1 text-sm leading-6 text-neutral-700">{body}</p>
    </div>
  );
}
